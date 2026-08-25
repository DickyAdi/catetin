import { Footer } from "@/components/sections/Footer";
import { Nav } from "@/components/sections/Nav";

const SECTIONS = [
  {
    title: "Data Apa yang Kami Simpan",
    body: "Kami simpan catatan jualan dan belanja yang kamu ketik, dan ID Telegram kamu. Kami tidak minta nomor rekening atau KTP.",
  },
  {
    title: "Untuk Apa Data Ini Dipakai",
    body: "Data dipakai supaya bot bisa hitung untung-rugi warungmu dan kirim ringkasan atau laporan.",
  },
  {
    title: "Siapa yang Bisa Lihat Data",
    body: "Hanya kamu yang bisa lihat catatanmu sendiri. Tim CatetIn tidak membagikan catatanmu ke orang lain.",
  },
  {
    title: "Berapa Lama Data Disimpan",
    body: "Pengguna Gratis: riwayat disimpan 30 hari. Pengguna Premium: riwayat disimpan tanpa batas waktu, selama akun aktif.",
  },
  {
    title: "Hak Kamu Sesuai UU PDP",
    body: "Kamu berhak minta lihat, ubah, atau hapus semua catatanmu kapan saja. Cukup chat tim kami untuk minta ini.",
  },
  {
    title: "Kontak",
    body: "Ada pertanyaan soal data kamu? Kirim email ke halo@catetin.id.",
  },
];

export function KebijakanPrivasi() {
  return (
    <div>
      <Nav />
      <section className="mx-auto max-w-content px-lg pb-section pt-xl dark:bg-surface-dark">
        <h1 className="mb-md text-center text-display-md dark:text-on-dark">Kebijakan Privasi</h1>
        <p className="mx-auto mb-xxl max-w-[560px] text-center text-body text-ink-muted dark:text-on-dark-muted">
          Ringkasan sederhana soal data kamu di CatetIn, sesuai UU Pelindungan Data
          Pribadi (UU PDP).
        </p>

        <div className="mx-auto flex max-w-[720px] flex-col gap-lg">
          {SECTIONS.map((section) => (
            <div
              key={section.title}
              className="rounded-card border border-hairline bg-surface-white p-lg dark:border-surface-dark-soft dark:bg-surface-dark-soft"
            >
              <h2 className="mb-xs text-body-strong dark:text-on-dark">{section.title}</h2>
              <p className="text-body text-ink-muted dark:text-on-dark-muted">{section.body}</p>
            </div>
          ))}
        </div>
      </section>
      <Footer />
    </div>
  );
}

export default KebijakanPrivasi;
