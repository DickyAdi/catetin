const PROBLEMS = [
  {
    title: "Lupa Catat Jualan",
    body: "Ujung bulan bingung, uang habis ke mana.",
  },
  {
    title: "Excel Ribet",
    body: "Buka laptop dan hitung rumus cuma buat catat jualan.",
  },
  {
    title: "Untung-Rugi Tidak Jelas",
    body: "Jualan tiap hari, tapi tidak tahu untung berapa.",
  },
];

export function ProblemCards() {
  return (
    <section className="mx-auto max-w-content px-lg pb-section">
      <h2 className="mb-xxl text-center text-display-md">Sering Kejadian, Kan?</h2>
      <div className="flex flex-wrap justify-center gap-lg">
        {PROBLEMS.map((problem) => (
          <div
            key={problem.title}
            className="min-w-[260px] max-w-[320px] flex-1 rounded-card border border-hairline bg-surface-white p-lg"
          >
            <h3 className="mb-xs text-body-strong">{problem.title}</h3>
            <p className="text-body-small text-ink-muted">{problem.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
