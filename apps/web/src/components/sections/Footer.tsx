import { Link } from "react-router-dom";

export function Footer() {
  return (
    <footer className="border-t border-surface-dark-soft bg-surface-dark px-lg py-xxl text-on-dark">
      <div className="mx-auto flex max-w-content flex-wrap items-center justify-between gap-lg">
        <div className="flex flex-col gap-sm">
          <img
            src="/assets/5_CatetIn_Dark_Logo_Transparent.svg"
            alt="CatetIn"
            width={120}
            height={32}
            className="h-8 w-auto object-contain"
          />
          <p className="text-body-small text-on-dark-muted">© 2026 CatetIn</p>
        </div>
        <div className="flex gap-lg">
          <Link
            to="/kebijakan-privasi"
            className="text-nav-link text-primary-on-dark no-underline hover:underline"
          >
            Kebijakan Privasi
          </Link>
          <a
            href="mailto:halo@catetin.id"
            className="text-nav-link text-primary-on-dark no-underline hover:underline"
          >
            Kontak
          </a>
        </div>
      </div>
    </footer>
  );
}
