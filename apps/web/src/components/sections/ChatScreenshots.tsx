import { BotBubble, Money, PhoneFrame, UserBubble } from "./ChatBubble";

const EXAMPLES = [
  {
    user: "jual ayam geprek 50rb",
    bot: (
      <>
        Tercatat! Ayam geprek <Money amount="50.000" sign="+" />
      </>
    ),
  },
  {
    user: "beli tepung 20rb",
    bot: (
      <>
        Tercatat! Beli tepung <Money amount="20.000" sign="-" />
      </>
    ),
  },
];

export function ChatScreenshots() {
  return (
    <section id="contoh" className="mx-auto max-w-content px-lg pb-section">
      <h2 className="mb-md text-center text-display-md">Contoh Percakapan</h2>
      <p className="mx-auto mb-xxl max-w-[560px] text-center text-body text-ink-muted">
        Kamu chat seperti biasa. Bot langsung catat dan hitung untung-rugimu.
      </p>
      <div className="flex flex-wrap justify-center gap-xl">
        {EXAMPLES.map((example) => (
          <PhoneFrame key={example.user} className="max-w-[320px]">
            <UserBubble>{example.user}</UserBubble>
            <BotBubble>{example.bot}</BotBubble>
          </PhoneFrame>
        ))}
      </div>
    </section>
  );
}
