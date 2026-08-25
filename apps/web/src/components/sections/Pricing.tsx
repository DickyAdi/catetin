import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export function Pricing() {
  return (
    <section id="harga" className="mx-auto max-w-content px-lg pb-section dark:bg-surface-dark">
      <h2 className="mb-xxl text-center text-display-md dark:text-on-dark">Pilih Paketmu</h2>
      <div className="flex flex-wrap justify-center gap-lg">
        <div className="min-w-[280px] max-w-[400px] flex-1 rounded-card border border-hairline bg-canvas p-xl dark:border-surface-dark-soft dark:bg-surface-dark-soft">
          <h3 className="mb-xs text-body-strong dark:text-on-dark">Gratis</h3>
          <p className="tabular-money mb-lg text-money-figure dark:text-on-dark">
            Rp 0
            <span className="text-body-small font-normal text-ink-muted dark:text-on-dark-muted">
              /bulan
            </span>
          </p>
          <ul className="space-y-sm text-body-small text-ink-muted dark:text-on-dark-muted">
            <li>Catat jualan harian tanpa batas</li>
            <li>Ringkasan untung-rugi harian</li>
            <li>Riwayat 30 hari terakhir</li>
          </ul>
        </div>

        <div className="min-w-[280px] max-w-[400px] flex-1 rounded-card bg-surface-white p-xl shadow-evidence dark:bg-surface-dark-soft">
          <h3 className="mb-xs text-body-strong dark:text-on-dark">Premium</h3>
          <p className="tabular-money mb-lg text-money-figure dark:text-on-dark">
            Rp 15.000
            <span className="text-body-small font-normal text-ink-muted dark:text-on-dark-muted">
              /bulan
            </span>
          </p>
          <ul className="mb-lg space-y-sm text-body-small text-ink-muted dark:text-on-dark-muted">
            <li>Semua fitur Gratis</li>
            <li>Laporan PDF bulanan (/lapor)</li>
            <li>Riwayat tanpa batas waktu</li>
            <li className="flex items-center gap-xs">
              Laporan keuangan lengkap (neraca)
              <Badge variant="placeholder">Menyusul</Badge>
            </li>
          </ul>
          <div className="flex flex-col gap-sm">
            <Button variant="primary" className="w-full" disabled>
              Segera Hadir
            </Button>
            <p className="text-center text-body-small text-ink-faint dark:text-on-dark-muted">
              Premium belum bisa dipesan. Coba dulu paket Gratis, ya.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
