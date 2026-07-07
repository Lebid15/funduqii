import { Card } from "@/components/ui/Card";
import { Container } from "@/components/layout/Container";
import { defaultLocale } from "@/lib/i18n/config";
import { getDictionary } from "@/lib/i18n/dictionaries";

/**
 * Temporary Phase 1 foundation page. It only confirms the frontend runs and
 * that the central i18n + design-token scaffolding works. This is NOT the
 * public website — that is built in Phase 12.
 */
export default function Home() {
  const dict = getDictionary(defaultLocale);

  return (
    <main className="foundation">
      <Container>
        <Card className="foundation__card">
          <span className="foundation__badge">{dict.app.phase}</span>
          <h1 className="foundation__title">{dict.app.name}</h1>
          <p className="foundation__subtitle">{dict.app.foundationReady}</p>
        </Card>
      </Container>
    </main>
  );
}
