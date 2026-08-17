import { Button } from "@/components/ui/button";
import { CTA_LABEL, TELEGRAM_URL } from "@/lib/constants";

export function Pricing() {
  return (
    <section id="harga" className="mx-auto max-w-content px-lg pb-section">
      <h2 className="mb-xxl text-center text-display-md">Pilih Paketmu</h2>
      <div className="flex flex-wrap justify-center gap-lg">
        <div className="min-w-[280px] max-w-[400px] flex-1 rounded-card border border-hairline bg-canvas p-xl">
          <h3 className="mb-xs text-body-strong">Gratis</h3>
          <p className="tabular-money mb-lg text-money-figure">
            Rp 0<span className="text-body-small font-normal text-ink-muted">/bulan</span>
          </p>
          <ul className="space-y-sm text-body-small text-ink-muted">
            <li>Catat jualan harian tanpa batas</li>
            <li>Ringkasan untung-rugi harian</li>
            <li>Riwayat 30 hari terakhir</li>
          </ul>
        </div>

        <div className="min-w-[280px] max-w-[400px] flex-1 rounded-card bg-surface-white p-xl shadow-evidence">
          <h3 className="mb-xs text-body-strong">Premium</h3>
          <p className="tabular-money mb-lg text-money-figure">
            Rp 15.000<span className="text-body-small font-normal text-ink-muted">/bulan</span>
          </p>
          <ul className="mb-lg space-y-sm text-body-small text-ink-muted">
            <li>Semua fitur Gratis</li>
            <li>Laporan PDF bulanan (/lapor)</li>
            <li>Riwayat tanpa batas waktu</li>
          </ul>
          <Button asChild variant="primary" className="w-full">
            <a href={TELEGRAM_URL} target="_blank" rel="noreferrer">
              {CTA_LABEL}
            </a>
          </Button>
        </div>
      </div>
    </section>
  );
}
