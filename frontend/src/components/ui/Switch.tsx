interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  disabled?: boolean;
  id?: string;
}

/** Central toggle. `label` is provided (translated) by the caller. */
export function Switch({ checked, onChange, label, disabled, id }: SwitchProps) {
  return (
    <label className="switch">
      <input
        id={id}
        type="checkbox"
        role="switch"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="switch__control" aria-hidden="true" />
      <span className="field__label">{label}</span>
    </label>
  );
}
