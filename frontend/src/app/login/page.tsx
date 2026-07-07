"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Hotel } from "lucide-react";

import { LanguageSwitcher } from "@/components/layout/LanguageSwitcher";
import {
  Alert,
  Button,
  Card,
  FormField,
  Icon,
  Input,
  PasswordInput,
} from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Central login screen — the first real entry to the platform console.
 * Credentials are exchanged for an HttpOnly-cookie session via the BFF login
 * route; no token ever touches JS or localStorage.
 */
export default function LoginPage() {
  const { t } = useI18n();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const response = await fetch("/api/session/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (response.ok) {
        router.replace("/platform");
        router.refresh();
        return;
      }
      const body = (await response.json().catch(() => ({}))) as {
        code?: string;
      };
      if (body.code === "not_platform_owner") {
        setError(t.auth.forbiddenNotOwner);
      } else if (response.status === 401) {
        setError(t.auth.invalidCredentials);
      } else {
        setError(t.auth.genericError);
      }
    } catch {
      setError(t.errors.network);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth">
      <Card className="auth__card">
        <div className="auth__brand">
          <span className="auth__brand-mark">
            <Icon icon={Hotel} size="lg" />
          </span>
          <div className="auth__brand-name">{t.app.name}</div>
          <div className="auth__brand-sub">{t.auth.loginSubtitle}</div>
        </div>

        <form className="auth__form" onSubmit={handleSubmit} noValidate>
          {error ? <Alert tone="error">{error}</Alert> : null}

          <FormField label={t.auth.email} htmlFor="email">
            <Input
              id="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              placeholder={t.auth.emailPlaceholder}
              onChange={(event) => setEmail(event.target.value)}
            />
          </FormField>

          <FormField label={t.auth.password} htmlFor="password">
            <PasswordInput
              id="password"
              autoComplete="current-password"
              required
              value={password}
              placeholder={t.auth.passwordPlaceholder}
              showLabel={t.auth.showPassword}
              hideLabel={t.auth.hidePassword}
              onChange={(event) => setPassword(event.target.value)}
            />
          </FormField>

          <Button type="submit" block loading={busy}>
            {busy ? t.auth.submitting : t.auth.submit}
          </Button>
        </form>

        <div className="auth__lang">
          <LanguageSwitcher />
        </div>
      </Card>
    </main>
  );
}
