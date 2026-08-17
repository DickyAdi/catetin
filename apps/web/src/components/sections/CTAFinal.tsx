import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { CTA_LABEL, TELEGRAM_URL } from "@/lib/constants";

export function CTAFinal() {
  return (
    <section className="mx-auto max-w-content px-lg pb-section text-center">
      <h2 className="mb-md text-display-md">Mulai Catat Jualanmu Hari Ini</h2>
      <p className="mb-xl text-body text-ink-muted">
        Gratis, langsung bisa dipakai di Telegram.
      </p>
      <Button asChild variant="primary" className="mb-md w-full desktop:w-auto">
        <a href={TELEGRAM_URL} target="_blank" rel="noreferrer">
          {CTA_LABEL}
        </a>
      </Button>
      <p className="text-body-small text-ink-faint">
        Datamu aman. Baca{" "}
        <Link to="/kebijakan-privasi" className="text-primary underline-offset-4 hover:underline">
          Kebijakan Privasi
        </Link>
        .
      </p>
    </section>
  );
}
