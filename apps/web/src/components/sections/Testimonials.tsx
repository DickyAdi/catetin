import { Button } from "@/components/ui/button";
import { CTA_LABEL, TELEGRAM_URL } from "@/lib/constants";

export function Testimonials() {
  return (
    <section className="mx-auto max-w-content px-lg pb-section dark:bg-surface-dark">
      <h2 className="mb-xs text-center text-display-md dark:text-on-dark">Kata Pengguna</h2>
      {/*
        Explicit 560px rather than Tailwind's `lg` container alias: this
        project's @theme defines a named --spacing-lg (24px), which shadows the
        default --container-lg in the max-width lookup, so the alias would
        compile to max-width:24px. 560px is the same centered-content width
        Hero and ChatScreenshots already use.
      */}
      <div className="mx-auto mt-xxl max-w-[560px] rounded-card border border-hairline bg-surface-white p-xl text-center dark:border-surface-dark-soft dark:bg-surface-dark-soft">
        <p className="text-4xl" aria-hidden="true">
          🙈
        </p>
        <p className="mt-md text-body text-ink dark:text-on-dark">
          Belum ada testimoni. Coba dulu, yuk, nanti kita tulis ceritamu di sini. 😊
        </p>
        <Button asChild variant="primary" size="utility" className="mt-lg">
          <a href={TELEGRAM_URL} target="_blank" rel="noreferrer">
            {CTA_LABEL}
          </a>
        </Button>
      </div>
    </section>
  );
}
