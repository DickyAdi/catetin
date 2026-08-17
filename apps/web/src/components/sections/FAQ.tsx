import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

const FAQS = [
  {
    question: "Amankah datanya?",
    answer: "Aman. Catatan jualanmu cuma bisa diakses olehmu, sesuai aturan UU PDP.",
  },
  {
    question: "Bisa buat warung kecil?",
    answer: "Bisa. CatetIn dibuat khusus untuk warung, jualan rumahan, dan reseller.",
  },
  {
    question: "Harus pintar teknologi?",
    answer: "Tidak. Kalau bisa chat di Telegram, kamu sudah bisa pakai CatetIn.",
  },
  {
    question: "Berapa biayanya?",
    answer:
      "Gratis untuk catat jualan harian. Paket Premium Rp 15.000 per bulan untuk laporan PDF.",
  },
  {
    question: "Bagaimana cara lihat laporan?",
    answer: "Ketik /lapor di chat, bot akan kirim laporan dalam bentuk PDF.",
  },
  {
    question: "Bisa pakai WhatsApp?",
    answer: "Belum bisa. Sekarang CatetIn baru ada di Telegram.",
  },
];

export function FAQ() {
  return (
    <section id="faq" className="mx-auto max-w-[720px] px-lg pb-section">
      <h2 className="mb-xl text-center text-display-md">Pertanyaan Umum</h2>
      <Accordion>
        {FAQS.map((faq) => (
          <AccordionItem key={faq.question}>
            <AccordionTrigger>{faq.question}</AccordionTrigger>
            <AccordionContent>{faq.answer}</AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </section>
  );
}
