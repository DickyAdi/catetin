import { CTAFinal } from "@/components/sections/CTAFinal";
import { BotBubble, Money, PhoneFrame, UserBubble } from "@/components/sections/ChatBubble";
import { Footer } from "@/components/sections/Footer";
import { Nav } from "@/components/sections/Nav";

const STEPS = [
  {
    title: "1. Buka Telegram, Cari @CatetInBot",
    body: "Ketik nama botnya di kolom pencarian Telegram, lalu tekan mulai.",
    example: (
      <BotBubble>Halo! Aku bantu catat jualan dan belanjamu di sini.</BotBubble>
    ),
  },
  {
    title: "2. Ketik Jualan Hari Ini",
    body: 'Tulis seperti chat biasa, contoh: "jual ayam geprek 50rb".',
    example: (
      <>
        <UserBubble>jual ayam geprek 50rb</UserBubble>
        <BotBubble>
          Tercatat! Ayam geprek <Money amount="50.000" sign="+" />
        </BotBubble>
      </>
    ),
  },
  {
    title: "3. Ketik Belanja Juga",
    body: 'Belanja bahan? Tulis juga, contoh: "beli tepung 20rb".',
    example: (
      <>
        <UserBubble>beli tepung 20rb</UserBubble>
        <BotBubble>
          Tercatat! Beli tepung <Money amount="20.000" sign="-" />
        </BotBubble>
      </>
    ),
  },
  {
    title: "4. Cek Untung-Rugi Kapan Saja",
    body: "Ketik /ringkasan, bot langsung kasih tahu untung hari ini.",
    example: (
      <>
        <UserBubble>/ringkasan</UserBubble>
        <BotBubble>
          Untung hari ini: <Money amount="130.000" sign="+" />
        </BotBubble>
      </>
    ),
  },
  {
    title: "5. Ambil Laporan Bulanan",
    body: "Pengguna Premium bisa ketik /lapor untuk laporan PDF bulanan.",
    example: <BotBubble>Laporan bulan ini sudah kukirim dalam bentuk PDF.</BotBubble>,
  },
];

export function CaraKerja() {
  return (
    <div>
      <Nav />
      <section className="mx-auto max-w-content px-lg pb-section pt-xl text-center">
        <h1 className="mb-md text-display-md">Cara Kerja CatetIn</h1>
        <p className="mx-auto max-w-[560px] text-body text-ink-muted">
          Lima langkah gampang, dari buka Telegram sampai tahu untung-rugimu.
        </p>
      </section>

      <section className="mx-auto max-w-content px-lg pb-section">
        <div className="flex flex-col gap-xl">
          {STEPS.map((step) => (
            <div
              key={step.title}
              className="flex flex-col items-center gap-lg rounded-card border border-hairline bg-surface-white p-xl desktop:flex-row desktop:items-start desktop:text-left"
            >
              <div className="flex-1 text-center desktop:text-left">
                <h2 className="mb-xs text-body-strong">{step.title}</h2>
                <p className="text-body text-ink-muted">{step.body}</p>
              </div>
              <PhoneFrame className="max-w-[300px] flex-1">{step.example}</PhoneFrame>
            </div>
          ))}
        </div>
      </section>

      <CTAFinal />
      <Footer />
    </div>
  );
}

export default CaraKerja;
