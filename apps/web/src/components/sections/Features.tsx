import { FileText, Lock, MessageCircle, TrendingUp } from "lucide-react";
import type { LucideIcon } from "lucide-react";

const FEATURES: { title: string; body: string; icon: LucideIcon }[] = [
  {
    title: "Tanpa Aplikasi Baru",
    body: "Cukup chat di Telegram, tidak perlu install apa-apa.",
    icon: MessageCircle,
  },
  {
    title: "Tanpa Excel",
    body: "Untung-rugi langsung terlihat, tidak perlu hitung manual.",
    icon: TrendingUp,
  },
  {
    title: "Data Cuma Punya Kamu",
    body: "Aman dan privat, sesuai aturan UU PDP.",
    icon: Lock,
  },
  {
    title: "Laporan Siap Dipakai",
    body: "Laporan untung-rugi rapi, siap buat kebutuhan usahamu.",
    icon: FileText,
  },
];

export function Features() {
  return (
    <section id="fitur" className="mx-auto max-w-content px-lg pb-section">
      <h2 className="mb-xxl text-center text-display-md">Kenapa CatetIn</h2>
      <div className="flex flex-wrap justify-center gap-lg">
        {FEATURES.map((feature) => (
          <div
            key={feature.title}
            className="min-w-[260px] max-w-[320px] flex-1 rounded-card border border-hairline bg-surface-white p-lg"
          >
            <div className="mb-md flex h-11 w-11 items-center justify-center rounded-secondary bg-primary-soft">
              <feature.icon className="h-[22px] w-[22px] text-primary" strokeWidth={2} />
            </div>
            <h3 className="mb-xs text-body-strong">{feature.title}</h3>
            <p className="text-body-small text-ink-muted">{feature.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
