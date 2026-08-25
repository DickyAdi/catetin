import { Button } from "@/components/ui/button";
import { CTA_LABEL, TELEGRAM_URL } from "@/lib/constants";
import { BotBubble, Money, PhoneFrame, UserBubble } from "./ChatBubble";

// No brand mark here on purpose: <Nav /> renders the full CatetIn logo immediately
// above this section, so a second logo would repeat the same mark inside one viewport
// and push the headline (the real hero) below the fold on mobile.
export function Hero() {
  return (
    <section className="mx-auto max-w-content px-lg pb-section pt-xl text-center dark:bg-surface-dark">
      <h1 className="mx-auto mb-lg text-hero-display-mobile desktop:text-hero-display dark:text-on-dark">
        Catat Untung-Rugi Warungmu, Langsung dari Chat
      </h1>
      <p className="mx-auto mb-xl max-w-[560px] text-lead text-ink-muted dark:text-on-dark-muted">
        Tanpa Excel, tanpa aplikasi baru. Ketik jualanmu seperti chat biasa di Telegram.
      </p>
      <Button asChild variant="primary" className="mb-xxl w-full desktop:w-auto">
        <a href={TELEGRAM_URL} target="_blank" rel="noreferrer">
          {CTA_LABEL}
        </a>
      </Button>

      <PhoneFrame>
        <UserBubble>jual ayam geprek 50rb</UserBubble>
        <BotBubble>
          Tercatat! Ayam geprek <Money amount="50.000" sign="+" />
          <br />
          Untung hari ini: <Money amount="180.000" sign="+" />
        </BotBubble>
      </PhoneFrame>
    </section>
  );
}
