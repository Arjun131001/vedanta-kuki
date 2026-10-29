import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

type Option = { value: string; label: string };

export default function Select({ value, options, onChange, label, disabled = false }: {
  value: string;
  options: Option[];
  onChange: (value: string) => void;
  label: string;
  disabled?: boolean;
}) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const search = useRef({ text: "", time: 0 });
  const [open, setOpen] = useState(false);
  const selected = options.findIndex((option) => option.value === value);
  const [active, setActive] = useState(Math.max(0, selected));
  const [position, setPosition] = useState({ left: 0, top: 0, width: 0, maxHeight: 280 });
  const expanded = open && !disabled && options.length > 0;

  useLayoutEffect(() => {
    if (!expanded) return;
    const place = () => {
      const bounds = trigger.current?.getBoundingClientRect();
      if (!bounds) return;
      const roomBelow = window.innerHeight - bounds.bottom - 16;
      const roomAbove = bounds.top - 16;
      const up = roomBelow < Math.min(280, options.length * 42 + 16) && roomAbove > roomBelow;
      const maxHeight = Math.max(48, Math.min(280, up ? roomAbove : roomBelow));
      const height = Math.min(maxHeight, menu.current?.scrollHeight || maxHeight);
      const width = Math.min(Math.max(bounds.width, 200), window.innerWidth - 24);
      setPosition({ left: Math.max(12, Math.min(bounds.left, window.innerWidth - width - 12)),
        top: up ? Math.max(12, bounds.top - height - 8) : bounds.bottom + 8, width, maxHeight });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [expanded, options.length]);

  useEffect(() => {
    if (!expanded) return;
    const outside = (event: PointerEvent) => {
      if (!trigger.current?.contains(event.target as Node) && !menu.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [expanded]);

  useEffect(() => {
    if (expanded) menu.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active, expanded]);

  const choose = (index: number) => {
    if (options[index]) onChange(options[index].value);
    setOpen(false);
    trigger.current?.focus();
  };
  const show = () => { setActive(Math.max(0, selected)); setOpen(true); };

  return <div className="modern-select">
    <button ref={trigger} type="button" role="combobox" aria-label={label}
      aria-haspopup="listbox" aria-expanded={expanded} aria-controls={`${id}-menu`}
      aria-activedescendant={expanded ? `${id}-option-${active}` : undefined}
      disabled={disabled || options.length === 0} className={`select-trigger ${expanded ? "is-open" : ""}`}
      onClick={() => expanded ? setOpen(false) : show()}
      onBlur={() => setOpen(false)}
      onKeyDown={(event) => {
        if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
          event.preventDefault();
          setOpen(true);
          setActive((current) => event.key === "Home" ? 0 : event.key === "End" ? options.length - 1
            : !expanded ? Math.max(0, selected) : Math.max(0, Math.min(options.length - 1, current + (event.key === "ArrowDown" ? 1 : -1))));
        } else if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          if (expanded) choose(active); else show();
        } else if (event.key === "Escape") {
          if (expanded) { event.preventDefault(); event.stopPropagation(); setOpen(false); }
        } else if (event.key === "Tab") setOpen(false);
        else if (event.key.length === 1 && !event.ctrlKey && !event.altKey && !event.metaKey) {
          const now = Date.now();
          search.current = { text: (now - search.current.time < 600 ? search.current.text : "") + event.key.toLocaleLowerCase(), time: now };
          const found = options.findIndex((option) => option.label.toLocaleLowerCase().startsWith(search.current.text));
          if (found >= 0) { event.preventDefault(); setActive(found); setOpen(true); }
        }
      }}>
      <span className="select-value">{options[selected]?.label || "Choose an option"}</span>
      <svg className="select-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="m7 10 5 5 5-5" /></svg>
    </button>
    {expanded && createPortal(<div ref={menu} id={`${id}-menu`} role="listbox" aria-label={label}
      className="select-menu" style={position} onMouseDown={(event) => event.preventDefault()}>
      {options.map((option, index) => <div key={option.value} id={`${id}-option-${index}`} role="option"
        aria-selected={option.value === value} data-index={index}
        className={`select-option ${index === active ? "is-active" : ""} ${option.value === value ? "is-selected" : ""}`}
        onPointerMove={() => setActive(index)} onClick={() => choose(index)}>
        <span>{option.label}</span>
        {option.value === value && <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="m5 12 4 4L19 6" /></svg>}
      </div>)}
    </div>, document.body)}
  </div>;
}
