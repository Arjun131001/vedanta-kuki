"""Exercise the persisted chat-to-worker flow using synthetic files and mocked HTTP."""
import io
import json
from dataclasses import replace

import httpx
import openpyxl
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.qa import answer_question
from app.store import Store
from app.worker import process_one, process_question


def test_chat_worker_followup_and_restart_without_external_requests(tmp_path):
    settings = replace(Settings(), data_dir=tmp_path, openai_api_key='mock-only')
    calls = []

    def upload(client, name, text):
        workbook = openpyxl.Workbook()
        workbook.active['A1'] = text
        stream = io.BytesIO()
        workbook.save(stream)
        response = client.post('/api/documents', files=[('files', (name, stream.getvalue()))])
        assert response.status_code == 202
        return response.json()['results'][0]['document']['id']

    def provider(request):
        payload = json.loads(json.loads(request.content)['messages'][1]['content'])
        calls.append(payload)
        assert 'UNSELECTED' not in json.dumps(payload)
        record = next(item for item in payload['evidence'] if '42 kWh' in item['quote'])
        text = 'The source reports electricity consumption of 42 kWh.' if not payload['history'] else 'The reported unit is kWh.'
        content = {'claims': [{'text': text, 'citation_ids': [record['id']]}], 'limitations': []}
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(content)}}]})

    def mocked_answer(question, evidence, history, model, key):
        with httpx.Client(transport=httpx.MockTransport(provider)) as client:
            return answer_question(question, evidence, history, model, key, client)

    with TestClient(create_app(settings)) as client:
        selected = upload(client, 'selected.xlsx', 'Acme electricity consumption 42 kWh.')
        upload(client, 'other.xlsx', 'UNSELECTED confidential source 999 kg.')
        store = Store(settings)
        assert process_one(store) and process_one(store)
        conversation = client.post('/api/qa/sessions', json={'document_ids': [selected]}).json()
        session_id = conversation['id']
        url = f'/api/qa/sessions/{session_id}/messages'
        request = {'question': 'What electricity consumption is reported?', 'request_id': 'first-turn'}
        first = client.post(url, json=request)
        assert first.status_code == 202
        assert client.post(url, json=request).json()['id'] == first.json()['id']
        assert process_question(store, caller=mocked_answer)
        saved = client.get(f'/api/qa/sessions/{session_id}').json()['messages'][0]
        assert saved['status'] == 'ready' and '42 kWh' in saved['answer']
        assert saved['citations'][0]['document_id'] == selected
        assert saved['citations'][0]['filename'] == 'selected.xlsx'
        assert any('unreviewed' in item.lower() for item in saved['limitations'])
        followup = client.post(url, json={'question': 'Which unit is reported?', 'request_id': 'followup'})
        assert followup.status_code == 202
        assert process_question(store, caller=mocked_answer)
        assert len(calls) == 2 and calls[1]['history'][0]['answer'] == saved['answer']

    with TestClient(create_app(settings)) as client:
        restored = client.get(f'/api/qa/sessions/{session_id}').json()
        assert restored['document_ids'] == [selected]
        assert len(restored['messages']) == 2
        assert all(turn['status'] == 'ready' for turn in restored['messages'])
        assert client.get('/api/qa/sessions').json()['sessions'][0]['id'] == session_id
