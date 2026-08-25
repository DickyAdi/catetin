import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { CTA_LABEL, TELEGRAM_URL } from "@/lib/constants";

export function CTAFinal() {
  return (
    <section className="mx-auto max-w-content px-lg pb-section text-center dark:bg-surface-dark">
      <h2 className="mb-md text-display-md dark:text-on-dark">Mulai Catat Jualanmu Hari Ini</h2>
      <p className="mb-xl text-body text-ink-muted dark:text-on-dark-muted">
        Gratis, langsung bisa dipakai di Telegram.
      </p>
      <Button asChild variant="primary" className="mb-md w-full desktop:w-auto">
        <a href={TELEGRAM_URL} target="_blank" rel="noreferrer">
          {CTA_LABEL}
        </a>
      </Button>
      <p className="text-body-small text-ink-faint dark:text-on-dark-muted">
        Datamu aman. Baca{" "}
        <Link
          to="/kebijakan-privasi"
          className="text-primary underline-offset-4 hover:underline dark:text-primary-on-dark"
        >
          Kebijakan Privasi
        </Link>
        .
      </p>
    </section>
  );
}
