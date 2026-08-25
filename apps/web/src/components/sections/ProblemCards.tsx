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
    <section className="mx-auto max-w-content px-lg pb-section dark:bg-surface-dark">
      <h2 className="mb-xxl text-center text-display-md dark:text-on-dark">Sering Kejadian, Kan?</h2>
      <div className="flex flex-wrap justify-center gap-lg">
        {PROBLEMS.map((problem) => (
          <div
            key={problem.title}
            className="min-w-[260px] max-w-[320px] flex-1 rounded-card border border-hairline bg-surface-white p-lg dark:border-surface-dark-soft dark:bg-surface-dark-soft"
          >
            <h3 className="mb-xs text-body-strong dark:text-on-dark">{problem.title}</h3>
            <p className="text-body-small text-ink-muted dark:text-on-dark-muted">{problem.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
