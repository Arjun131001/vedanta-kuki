import io, json
from dataclasses import replace
import httpx, openpyxl, pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.store import Store
from app.worker import process_one
from app import qa_store
from app.qa import answer_question, fy_bounds
from app.facts import FactError


def make_doc(client,text):
    book=openpyxl.Workbook(); book.active['A1']=text; book.active['B1']=42
    data=io.BytesIO(); book.save(data)
    return client.post('/api/documents',files=[('files',(text+'.xlsx',data.getvalue()))]).json()['results'][0]['document']


def test_scope_persistence_idempotency(tmp_path):
    config=replace(Settings(),data_dir=tmp_path,openai_api_key='test-key')
    with TestClient(create_app(config)) as client:
        first=make_doc(client,'alpha'); other=make_doc(client,'unrelated'); store=Store(config)
        assert process_one(store) and process_one(store)
        assert client.post('/api/qa/sessions',json={'document_ids':[first['id'],'missing']}).status_code==400
        sid=client.post('/api/qa/sessions',json={'document_ids':[first['id']]}).json()['id']
        payload={'question':'What is alpha?','request_id':'request-1'}
        turn=client.post(f'/api/qa/sessions/{sid}/messages',json=payload).json()
        assert client.post(f'/api/qa/sessions/{sid}/messages',json=payload).json()['id']==turn['id']
        assert client.post(f'/api/qa/sessions/{sid}/messages',json={'question':'another','request_id':'request-2'}).status_code==409
        job=qa_store.claim(store); frozen=json.loads(job['evidence_json'])
        assert frozen['document_ids']==[first['id']] and all(r['document_id']==first['id'] for r in frozen['records'])
        assert other['id'] not in json.dumps(frozen)
        citation=frozen['records'][0]
        assert qa_store.finish(store,job,result={'answer':'Supported [1]','citations':[citation],'limitations':[]})
    with TestClient(create_app(config)) as client:
        assert client.get(f'/api/qa/sessions/{sid}').json()['messages'][0]['status']=='ready'
        assert len(client.get('/api/qa/sessions').json()['sessions'])==1
        assert client.post(f'/api/qa/sessions/{sid}/messages',json={'question':'different','request_id':'request-1'}).status_code==400


def test_expired_turn_fenced(tmp_path):
    config=replace(Settings(),data_dir=tmp_path,openai_api_key='test-key',lease_seconds=10)
    with TestClient(create_app(config)) as client:
        doc=make_doc(client,'alpha'); store=Store(config); assert process_one(store)
        sid=client.post('/api/qa/sessions',json={'document_ids':[doc['id']]}).json()['id']
        turn=client.post(f'/api/qa/sessions/{sid}/messages',json={'question':'What is alpha?','request_id':'a'}).json()
        start=turn['created_at']+1; job=qa_store.claim(store,now=start)
        assert qa_store.claim(store,now=start+11) is None
        assert not qa_store.finish(store,job,result={'answer':'stale','citations':[],'limitations':[]},now=start+12)
        assert client.get(f'/api/qa/sessions/{sid}').json()['messages'][0]['status']=='failed'


def test_missing_key_never_queues(tmp_path):
    config=replace(Settings(),data_dir=tmp_path,openai_api_key='')
    with TestClient(create_app(config)) as client:
        doc=make_doc(client,'alpha'); assert process_one(Store(config))
        sid=client.post('/api/qa/sessions',json={'document_ids':[doc['id']]}).json()['id']
        assert client.post(f'/api/qa/sessions/{sid}/messages',json={'question':'hello','request_id':'x'}).status_code==503
        assert client.get(f'/api/qa/sessions/{sid}').json()['messages']==[]
        calc=client.post(f'/api/qa/sessions/{sid}/messages',json={'question':'What is the total for financial year 2024?','request_id':'fy'})
        assert calc.status_code==202
        store=Store(config); job=qa_store.claim(store)
        from app.qa import answer_question
        result=answer_question(job['question'],json.loads(job['evidence_json']),[],'model','',client=None)
        assert qa_store.finish(store,job,result=result)
        assert client.get(f'/api/qa/sessions/{sid}').json()['messages'][0]['status']=='ready'


def test_mocked_claims_citations_and_scope():
    evidence={'records':[{'id':'doc:a','document_id':'doc','filename':'a.pdf','unit_index':1,'unit_label':'Page 1','reference_id':'a','quote':'Energy 42 kWh','cells':[],'evidence_status':'source_text_unreviewed'}],'warnings':[]}
    def response(claims): return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'claims':claims,'limitations':[]})}}]}
    def handler(req):
        body=json.loads(req.content); assert not body['store'] and body['response_format']['json_schema']['strict']
        assert 'You are Harvey Specter' in body['messages'][0]['content']
        return httpx.Response(200,json=response([{'text':'Energy was 42 kWh.','citation_ids':['doc:a']}]))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result=answer_question('What energy?',evidence,[],'gpt-4o-mini','secret',client)
        assert result['answer']=='Energy was 42 kWh. [1]' and result['citations'][0]['evidence_status']=='source_text_unreviewed'
    for claim in [{'text':'Energy was 43 kWh.','citation_ids':['doc:a']},{'text':'Energy was 42.','citation_ids':['other:a']},{'text':'Energy was 42.','citation_ids':[]}]:
        with httpx.Client(transport=httpx.MockTransport(lambda _,c=claim:httpx.Response(200,json=response([c])))) as client:
            with pytest.raises(FactError): answer_question('What energy?',evidence,[],'model','key',client)


def test_calculation_uses_local_engine_without_provider_and_refusal_handled():
    evidence={'records':[{'id':'d:a','document_id':'d','filename':'a.xlsx','quote':'January 2026 Total Consumption (kWh) 10','cells':['F3'],'unit_index':1},
                         {'id':'d:b','document_id':'d','filename':'a.xlsx','quote':'ANNUAL TOTAL Total Consumption (kWh) 10','cells':['F16'],'unit_index':1}],'warnings':[]}
    with httpx.Client(transport=httpx.MockTransport(lambda _:pytest.fail('provider called'))) as client:
        result=answer_question('Calculate whether monthly values and annual summaries agree',evidence,[],'model','key',client)
        assert result['calculations'] and result['calculations'][0]['kind']=='calculated'
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'refusal':'no'}}]}))) as client:
        with pytest.raises(FactError): answer_question('What is reported?',evidence,[],'model','key',client)
    assert fy_bounds(2024)==('2024-04-01','2025-03-31')


def test_lookup_total_is_not_blocked_and_source_qualifier_is_preserved():
    from app.qa import requires_calculation
    assert not requires_calculation("What is the total water bill?")
    assert requires_calculation("What is the total for financial year 2024?")
    evidence={'records':[{'id':'doc:a','quote':'Energy <42 kWh'}],'warnings':[]}
    result={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'claims':[{'text':'Energy was 42 kWh','citation_ids':['doc:a']}],'limitations':[]})}}]}
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=result))) as client:
        with pytest.raises(FactError): answer_question('What energy?',evidence,[],'model','key',client)


@pytest.mark.parametrize("claim,quote", [("42 million kWh","42 kWh"),("42%","42 kWh"),("42 tonnes","42 kWh"),("42","<42"),("42","42%"),("42 kWh was greater than 30 kWh","42 kWh and 30 kWh")])
def test_quantity_mismatch_and_derived_comparison_rejected(claim, quote):
    evidence={'records':[{'id':'d:a','quote':quote,'evidence_status':'source_text_unreviewed'}],'warnings':[]}
    result={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'claims':[{'text':claim,'citation_ids':['d:a']}],'limitations':[]})}}]}
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=result))) as client:
        with pytest.raises(FactError): answer_question('What was reported?',evidence,[],'model','key',client)


def test_spreadsheet_unit_can_only_be_taken_from_explicitly_cited_header():
    from app.qa import validate_claim_text
    value={'quote':'2425123','cells':['F16'],'document_id':'d','unit_index':1,'reference_id':'s1:F16'}
    header={'quote':'Total consumption (kWh)','cells':['F2'],'document_id':'d','unit_index':1,'reference_id':'s1:F2'}
    validate_claim_text("2425123 kWh", [value,header])
    with pytest.raises(FactError): validate_claim_text("2425123 tonnes", [value,header])
    with pytest.raises(FactError): validate_claim_text("2425123 kWh", [value])


@pytest.mark.parametrize("claim,quote", [("9,99,999 kWh","Energy 42 kWh"),("FY9999 energy","Energy 42 kWh"),("42 million kWh","42 million kg"),("42 Cubic Meters","42 litres")])
def test_numeric_formats_scales_and_units_must_be_cited_exactly(claim,quote):
    from app.qa import validate_claim_text
    with pytest.raises(FactError): validate_claim_text(claim,[{'quote':quote,'cells':[]}])


def test_unit_header_must_match_same_document_sheet_and_column():
    from app.qa import validate_claim_text
    value={'quote':'42','cells':['F16'],'document_id':'d','unit_index':1,'reference_id':'s1:F16'}
    for changed in ({'document_id':'other'},{'unit_index':2,'reference_id':'s2:F2'},{'cells':['G2'],'reference_id':'s1:G2'},{'cells':['F17'],'reference_id':'s1:F17'}):
        header={'quote':'Consumption (kg)','cells':['F2'],'document_id':'d','unit_index':1,'reference_id':'s1:F2',**changed}
        with pytest.raises(FactError): validate_claim_text('42 kg',[value,header])


def test_citations_are_always_unreviewed_and_automatically_warn():
    evidence={'records':[{'id':'doc:a','quote':'Energy 42 kWh','cells':[],'evidence_status':'source_text_unreviewed'}],'warnings':[]}
    payload={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'claims':[{'text':'Energy 42 kWh','citation_ids':['doc:a']}],'limitations':[]})}}]}
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=payload))) as client:
        answer=answer_question('What energy?',evidence,[],'model','key',client)
        assert any('unreviewed' in warning for warning in answer['limitations'])


def test_retrieval_keeps_annual_value_with_header_and_row_context(tmp_path):
    config=replace(Settings(),data_dir=tmp_path,openai_api_key='test-key')
    book=openpyxl.Workbook(); sheet=book.active
    sheet['F2']='Total Electricity Consumption (kWh)'; sheet['A16']='Annual Total'; sheet['F16']=2425123
    for row in range(3,205):
        if row != 16: sheet[f'F{row}']=row; sheet[f'A{row}']='Monthly'
    buffer=io.BytesIO(); book.save(buffer)
    with TestClient(create_app(config)) as client:
        doc=client.post('/api/documents',files=[('files',('annual.xlsx',buffer.getvalue()))]).json()['results'][0]['document']
        store=Store(config); assert process_one(store)
        sid=client.post('/api/qa/sessions',json={'document_ids':[doc['id']]}).json()['id']
        assert client.post(f'/api/qa/sessions/{sid}/messages',json={'question':'What is annual total electricity consumption?','request_id':'q'}).status_code==202
        job=qa_store.claim(store); snapshot=json.loads(job['evidence_json'])
        ids={r['reference_id'] for r in snapshot['records']}
        assert {'s1:F16','s1:F2','s1:A16'} <= ids
        assert all(record['evidence_status']=='source_text_unreviewed' for record in snapshot['records'])
        assert any('limited' in warning for warning in snapshot['warnings'])


def test_indian_grouping_must_match_verbatim_and_is_not_skipped():
    from app.qa import validate_claim_text
    validate_claim_text('9,99,999 kWh',[{'quote':'Total 9,99,999 kWh','cells':[]}])
    with pytest.raises(FactError): validate_claim_text('9,99,998 kWh',[{'quote':'Total 9,99,999 kWh','cells':[]}])

@pytest.mark.parametrize('text', ['Invoice HYD-WB-2025-12-001', 'Due 31st', 'Bill date 01-12-2025'])
def test_compound_identifiers_and_dates_must_be_exactly_cited(text):
    from app.qa import validate_claim_text
    validate_claim_text(text, [{'quote': text, 'cells': []}])
    with pytest.raises(FactError):
        validate_claim_text(text, [{'quote': text.replace('1', '9'), 'cells': []}])


def test_partial_claims_quarantined_and_no_invalid_citations_leak():
    evidence = {'records':[{'id':'d:a','quote':'Energy 42 kWh','cells':[], 'evidence_status':'source_text_unreviewed'}], 'warnings':[], 'sha256':'hash'}
    claims = [{'text':'Energy 42 kWh', 'citation_ids':['d:a']}, {'text':'Energy 99 kWh', 'citation_ids':['d:a']}, {'text':'secret', 'citation_ids':['other:a']}]
    payload = {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'claims':claims,'limitations':[]})}}]}
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=payload))) as client:
        result = answer_question('What energy?',evidence,[],'model','key',client)
    assert result['answer'] == 'Energy 42 kWh [1]'
    assert [c['id'] for c in result['citations']] == ['d:a']
    assert any('omitted' in item for item in result['limitations'])
    assert json.loads(result['_qa_audit']['proposal'])['claims'] == claims


def test_local_overview_is_extractive_without_provider():
    evidence = {'records':[{'id':'d:a','document_id':'d','filename':'a.pdf','quote':'Billing period date 01-12-2025'}], 'document_ids':['d'], 'warnings':[]}
    from app.qa import local_overview
    result = local_overview('What all details are there in documents?', evidence)
    assert 'Billing period date 01-12-2025' in result['answer']
    assert 'not a complete summary' in result['limitations'][0]


def test_private_proposal_persists_and_replays_without_altering_snapshot(tmp_path):
    config=replace(Settings(),data_dir=tmp_path,openai_api_key='test-key')
    with TestClient(create_app(config)) as client:
        doc=make_doc(client,'alpha'); store=Store(config); assert process_one(store)
        sid=qa_store.create_session(store,[doc['id']])['id']
        turn=qa_store.enqueue(store,sid,'What is alpha?','request')
        job=qa_store.claim(store); evidence=json.loads(job['evidence_json'])
        proposal=json.dumps({'claims':[{'text':'alpha','citation_ids':[evidence['records'][0]['id']]}],'limitations':[]})
        audit={'proposal':proposal,'evidence_sha256':evidence['sha256'],'model':'model','prompt_sha256':'prompt'}
        assert qa_store.finish(store,job,error='validation failed',audit=audit)
        qa_store.replay_saved_proposal(store,turn['id'])
        with store.connect() as db:
            row=db.execute('SELECT * FROM qa_turns WHERE id=?',(turn['id'],)).fetchone()
            assert json.loads(row['audit_json']) == audit
            assert row['evidence_json'] == job['evidence_json']
            assert row['status']=='ready'
        assert 'audit_json' not in qa_store.session(store,sid)['messages'][0]

@pytest.mark.parametrize('claim,quote', [('Includes 2025 billing details','Billing year 2025'), ('Invoice number 123 is stated','Invoice 123 Date')])
def test_ordinary_words_after_number_are_not_units(claim, quote):
    from app.qa import validate_claim_text
    validate_claim_text(claim, [{'quote':quote,'cells':[]}])


def test_unknown_unit_is_not_invented():
    from app.qa import validate_claim_text
    with pytest.raises(FactError):
        validate_claim_text('42 widgets', [{'quote':'Total 42 gadgets','cells':[]}])


def test_recover_failed_broad_question_audits_previous_turn(tmp_path):
    config=replace(Settings(), data_dir=tmp_path)
    store=Store(config)
    evidence={'records':[{'id':'d:p1:l1','document_id':'d','filename':'file.pdf','quote':'Energy consumption recorded 42 kWh'}], 'document_ids':['d'], 'warnings':[], 'sha256':'frozen'}
    with store.connect() as db:
        db.execute('INSERT INTO qa_sessions VALUES (?,?,?,?,?)',('s','title',json.dumps(['d']),1,1))
        db.execute("INSERT INTO qa_turns(id,session_id,request_id,question,status,evidence_json,history_json,model,error,created_at,updated_at) VALUES (?,?,?,?,'failed',?,? ,?,?,?,?)", ('t','s','r','What all details are there in documents?',json.dumps(evidence),'[]','model','old failure',1,1))
    result=qa_store.recover_local_overview(store,'t')
    assert 'Energy consumption recorded 42 kWh' in result['answer']
    with store.connect() as db:
        old=db.execute('SELECT * FROM qa_local_history WHERE turn_id=?',('t',)).fetchone()
        assert json.loads(old['previous_json'])['error']=='old failure'
        row=db.execute('SELECT * FROM qa_turns WHERE id=?',('t',)).fetchone()
        assert row['status']=='ready' and json.loads(row['evidence_json'])==evidence


def test_year_prose_and_unknown_unit_checks():
    from app.qa import validate_claim_text
    validate_claim_text('Includes 2025 sustainability reporting', [{'quote':'Billing year 2025', 'cells':[]}])
    with pytest.raises(FactError):
        validate_claim_text('Energy 42 widgets', [{'quote':'Energy 42 kWh', 'cells':[]}])


def test_overview_prioritizes_substantive_excerpts_and_specific_question_not_hijacked():
    from app.qa import local_overview
    quotes = ['Electricity Consumption', 'Bank details IFSC ABC123', 'Units consumed 2321 Cubic Meters', 'Billing period 01-12-2025 to 31-12-2025', 'Total amount due 50.00', 'We never compromise on food safety and compliance.']
    records = [{'id':f'd:{i}','document_id':'d','filename':'example.pdf','quote':q} for i,q in enumerate(quotes)]
    evidence = {'records':records, 'document_ids':['d'], 'warnings':[]}
    result = local_overview('What all details are there in documents?', evidence)
    assert result['answer'].startswith('Local source overview (selected excerpts)')
    assert all(q in result['answer'] for q in quotes[2:])
    assert quotes[0] not in result['answer'] and quotes[1] not in result['answer']
    assert local_overview('Summarize food safety commitments in the documents', evidence) is None


def test_overview_balances_primary_document_facets_over_generic_charges():
    from app.qa import local_overview
    quotes = ['Quality surcharge water energy total 10.00', 'Contact: Email details available online', 'Units Consumed 2321 Cubic Meters', 'Billing Period 01-12-2025 to 31-12-2025', 'Total Amount Due 50.00', 'Invoice Date 31-12-2025', 'Policy commitment: We will protect safety and quality.']
    records = [{'id':f'd:{i}', 'document_id':'d', 'filename':'example.pdf', 'quote':q} for i,q in enumerate(quotes)]
    result=local_overview('Give me an overview of selected documents', {'records':records, 'document_ids':['d'], 'warnings':[]})
    assert [r['quote'] for r in result['citations']] == quotes[2:]
    assert quotes[1] not in result['answer']


@pytest.mark.parametrize('claim,quote', [
    ('The invoice identifier is HYD-WB-2025-12-001.', 'Invoice Number: HYD-WB-2025-12-001'),
    ('The due date is the 31st.', 'Payment due on 31st of the month'),
    ('The policy references ISO9001.', 'Standard ISO9001 certification'),
    ('The policy references FSSC22000.', 'FSSC22000 food safety standard'),
])
def test_paraphrased_compound_identifiers_require_exact_source(claim, quote):
    from app.qa import validate_claim_text
    validate_claim_text(claim, [{'quote':quote,'cells':[]}])
    with pytest.raises(FactError):
        validate_claim_text(claim, [{'quote':'Unrelated document with no matching identifier', 'cells':[]}])


def test_unit_with_digit_still_requires_matching_quantity_and_unit():
    from app.qa import validate_claim_text
    validate_claim_text('Volume 42 m3', [{'quote':'Volume 42 m3','cells':[]}])
    with pytest.raises(FactError):
        validate_claim_text('Volume 43 m3', [{'quote':'Volume 42 m3','cells':[]}])
    with pytest.raises(FactError):
        validate_claim_text('Volume 42 m3', [{'quote':'Volume 42 kg','cells':[]}])


def test_broad_ai_response_used_when_valid_and_local_fallback_when_invalid():
    evidence={'records':[{'id':'d:a','document_id':'d','filename':'file.pdf','quote':'Energy consumption is 42 kWh','cells':[], 'evidence_status':'source_text_unreviewed'}], 'document_ids':['d'], 'warnings':[], 'sha256':'frozen'}
    for proposed, expected in [('Energy consumption is 42 kWh', 'Energy consumption is 42 kWh [1]'), ('Energy consumption is 99 kWh', 'Local source overview (selected excerpts)')]:
        calls=[]
        raw=json.dumps({'claims':[{'text':proposed,'citation_ids':['d:a']}], 'limitations':[]})
        def respond(request):
            calls.append(request)
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':raw}}]})
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            result=answer_question('Give an overview of selected documents', evidence, [], 'model', 'test-key', client)
        assert len(calls)==1 and result['answer'].startswith(expected)
        assert result['_qa_audit']['proposal']==raw
        if '99' in proposed:
            assert result['_qa_audit']['rejections'] and any('selected locally' in w for w in result['limitations'])


def test_broad_provider_error_does_not_fallback():
    evidence={'records':[{'id':'d:a','document_id':'d','filename':'a.pdf','quote':'Energy consumption 42 kWh'}], 'document_ids':['d'], 'warnings':[]}
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(429))) as client:
        with pytest.raises(FactError):
            answer_question('Give an overview of documents',evidence,[],'model','key',client)


def test_overview_joins_cited_consecutive_policy_lines_without_contact_or_copyright():
    from app.qa import local_overview
    values=[('p3:b2:l7','We never compromise on food safety and'),('p3:b2:l8','compliance. We adhere to international standards.'),('p1:l4','billing@example.org Please refer to Invoice Number 12345'),('p1:l5','Copyright © 2026 all rights reserved'),('p1:l6','This is a very long document title without any actual statement')]
    records=[{'id':'d:'+ref,'document_id':'d','filename':'policy.pdf','reference_id':ref,'quote':quote} for ref,quote in values]
    result=local_overview('Give an overview of selected documents',{'records':records,'document_ids':['d'],'warnings':[]})
    assert 'We never compromise on food safety and compliance.' in result['answer']
    assert [r['reference_id'] for r in result['citations']] == ['p3:b2:l7','p3:b2:l8']
    assert '@' not in result['answer'] and '©' not in result['answer'] and 'document title' not in result['answer']


def test_refresh_local_overview_archives_old_projection(tmp_path):
    config=replace(Settings(),data_dir=tmp_path); store=Store(config)
    evidence={'records':[{'id':'d:p1:l1','document_id':'d','filename':'file.pdf','quote':'Energy consumption recorded 42 kWh'}], 'document_ids':['d'],'warnings':[]}
    with store.connect() as db:
        db.execute('INSERT INTO qa_sessions VALUES (?,?,?,?,?)',('s','title',json.dumps(['d']),1,1))
        db.execute("INSERT INTO qa_turns(id,session_id,request_id,question,status,evidence_json,history_json,model,answer,created_at,updated_at) VALUES (?,?,?,?,'ready',?,?,?, ?,?,?)",('t','s','r','Overview of documents',json.dumps(evidence),'[]','model','Local source overview (selected excerpts)\n\nold',1,1))
    result=qa_store.refresh_local_overview(store,'t')
    assert '42 kWh' in result['answer']
    with store.connect() as db:
        history=db.execute('SELECT * FROM qa_local_history WHERE turn_id=?',('t',)).fetchone()
        assert 'old' in json.loads(history['previous_json'])['answer']
        assert history['action']=='refresh_extractive_overview'


def test_overview_skips_fragments_and_reused_policy_lines():
    from app.qa import local_overview
    values=[('p3:b2:l5','delivery to point of consumption. At every'),('p3:b2:l7','We never compromise on food safety and'),('p3:b2:l8','compliance. We adhere to international'),('p3:b2:l9','requirements. We will keep improving.'),('p3:b2:l10','requirements. We shall comply with the'),('p3:b2:l11','rules.'),('p3:b2:l12','quality we design is quality we deliver.')]
    records=[{'id':'d:'+ref,'document_id':'d','filename':'policy.pdf','reference_id':ref,'quote':quote} for ref,quote in values]
    result=local_overview('Overview of documents',{'records':records,'document_ids':['d'],'warnings':[]})
    assert 'We never compromise on food safety and compliance.' in result['answer']
    assert result['answer'].count('compliance.') == 1
    assert 'delivery to point' not in result['answer'] and 'requirements.' not in result['answer']
    assert 'quality we design' not in result['answer']


def test_multiple_cited_claims_are_readable_bullets_and_limitations_are_bounded():
    evidence={'records':[{'id':'d:a','quote':'Energy 42 kWh','cells':[],'evidence_status':'source_text_unreviewed'}, {'id':'d:b','quote':'Water 25 litres','cells':[],'evidence_status':'source_text_unreviewed'}], 'warnings':[]}
    raw={'claims':[{'text':'Energy 42 kWh','citation_ids':['d:a']},{'text':'Water 25 litres','citation_ids':['d:b']}], 'limitations':['Cannot determine the reporting period.','Cannot determine the 2025 total.']}
    body={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(raw)}}]}
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=body))) as client:
        result=answer_question('What did the document report?',evidence,[],'model','key',client)
    assert result['answer']=='- Energy 42 kWh [1]\n- Water 25 litres [2]'
    assert any('Model-reported limitation: Cannot determine the reporting period.' == w for w in result['limitations'])
    assert not any('2025' in w for w in result['limitations'])


def test_no_evidence_has_clear_response_without_provider():
    evidence={'records':[],'warnings':['The source has no readable text.']}
    with httpx.Client(transport=httpx.MockTransport(lambda _:pytest.fail('provider called'))) as client:
        result=answer_question('What was reported?',evidence,[],'model','key',client)
    assert 'couldn’t find' in result['answer'] and result['limitations']==evidence['warnings']


def test_empty_claims_have_friendly_scoped_response():
    evidence={'records':[{'id':'d:a','quote':'Energy consumption 42 kWh','cells':[]}], 'warnings':[]}
    raw={'claims':[],'limitations':['Cannot determine the period.']}
    payload={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(raw)}}]}
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=payload))) as client:
        result=answer_question('What period was reported?',evidence,[],'model','key',client)
    assert 'selected excerpts' in result['answer']
    assert any('Cannot determine the period' in item for item in result['limitations'])
