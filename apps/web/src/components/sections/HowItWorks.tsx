const STEPS = [
  {
    number: "1",
    title: "Buka Telegram",
    body: "Cari @CatetInBot, lalu mulai chat seperti biasa.",
    userMsg: null,
    botMsg: "Halo! Ketik jualanmu, ya 😊",
  },
  {
    number: "2",
    title: "Ketik Jualanmu",
    body: "Tulis seperti chat biasa, contoh: jual ayam geprek 50rb.",
    userMsg: "jual ayam geprek 50rb",
    botMsg: null,
  },
  {
    number: "3",
    title: "Lihat Untung-Rugi",
    body: "Bot langsung catat dan kasih tahu untung hari ini.",
    userMsg: null,
    botMsg: "Tercatat! Untung hari ini: +Rp 180.000",
  },
] as const;

export function HowItWorks() {
  return (
    <section id="cara-kerja" className="bg-surface-dark px-lg py-section text-on-dark">
      <div className="mx-auto max-w-content">
        <h2 className="mb-xxl text-center text-display-md">Cara Kerja, 3 Langkah</h2>
        <div className="flex flex-wrap justify-center gap-xl">
          {STEPS.map((step) => (
            <div
              key={step.number}
              className="min-w-[260px] max-w-[320px] flex-1 rounded-tile bg-surface-dark-soft p-xl"
            >
              <div className="mb-sm text-display-md text-primary-on-dark">{step.number}</div>
              <h3 className="mb-xs text-body-strong">{step.title}</h3>
              <p className="mb-lg text-body-small text-on-dark-muted">{step.body}</p>
              <div className="rounded-[14px] bg-surface-dark p-sm">
                <div className="flex flex-col gap-xs rounded-[12px] bg-surface-dark-soft p-sm">
                  {step.userMsg && (
                    <div className="max-w-[85%] self-end rounded-[12px] bg-on-dark px-sm py-xs text-body-small text-ink">
                      {step.userMsg}
                    </div>
                  )}
                  {step.botMsg && (
                    <div className="max-w-[85%] self-start rounded-[12px] bg-primary-on-dark px-sm py-xs text-body-small text-surface-dark">
                      {step.botMsg}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
