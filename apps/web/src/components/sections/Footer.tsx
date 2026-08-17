import { Link } from "react-router-dom";

export function Footer() {
  return (
    <footer className="bg-surface-dark px-lg py-xxl text-on-dark">
      <div className="mx-auto flex max-w-content flex-wrap items-center justify-between gap-lg">
        <p className="text-body-small text-on-dark-muted">© 2026 CatetIn</p>
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
