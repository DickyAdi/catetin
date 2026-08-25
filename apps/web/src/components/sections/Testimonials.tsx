import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";

const TESTIMONIALS = [
  {
    quote: "Sekarang aku tahu untung tiap hari, tanpa buka Excel.",
    name: "Bu Rina",
    place: "Warung Mbok Rina, Purwokerto",
  },
  {
    quote: "Tinggal chat, langsung tercatat. Anak saya saja bisa pakai.",
    name: "Pak Yanto",
    place: "Toko Kelontong Barokah, Malang",
  },
  {
    quote: "Tidak perlu belajar aplikasi baru. Ini paling gampang.",
    name: "Mbak Sari",
    place: "Reseller Baju Sari Fashion, Solo",
  },
];

export function Testimonials() {
  return (
    <section className="mx-auto max-w-content px-lg pb-section dark:bg-surface-dark">
      <h2 className="mb-xs text-center text-display-md dark:text-on-dark">Kata Pengguna</h2>
      <p className="mb-xxl text-center text-body-small text-ink-faint dark:text-on-dark-muted">
        Contoh testimoni — belum dari pengguna asli.
      </p>
      <div className="flex flex-wrap justify-center gap-lg">
        {TESTIMONIALS.map((testimonial) => (
          <div
            key={testimonial.name}
            className="min-w-[260px] max-w-[320px] flex-1 rounded-card border border-hairline bg-surface-white p-lg dark:border-surface-dark-soft dark:bg-surface-dark-soft"
          >
            <Badge variant="placeholder" className="mb-md">
              Placeholder
            </Badge>
            <p className="mb-lg text-body text-ink dark:text-on-dark">
              &ldquo;{testimonial.quote}&rdquo;
            </p>
            <div className="flex items-center gap-sm">
              <Avatar>
                <AvatarFallback>{testimonial.name.charAt(0)}</AvatarFallback>
              </Avatar>
              <div>
                <p className="text-body-small font-bold text-ink dark:text-on-dark">
                  {testimonial.name}
                </p>
                <p className="text-body-small text-ink-muted dark:text-on-dark-muted">
                  {testimonial.place}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
