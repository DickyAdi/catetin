import { Menu } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Sheet, SheetClose, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { CTA_LABEL, TELEGRAM_URL } from "@/lib/constants";

const LINKS = [
  { href: "/#cara-kerja", label: "Cara Kerja" },
  { href: "/#harga", label: "Harga" },
  { href: "/#faq", label: "FAQ" },
];

export function Nav() {
  return (
    <nav className="mx-auto flex max-w-content items-center justify-between px-lg py-lg">
      <Link to="/" className="text-lead font-bold text-ink no-underline">
        CatetIn
      </Link>

      <div className="hidden items-center gap-xl desktop:flex">
        {LINKS.map((link) => (
          <a key={link.href} href={link.href} className="text-nav-link text-ink no-underline">
            {link.label}
          </a>
        ))}
      </div>

      <div className="hidden desktop:block">
        <Button asChild variant="primary" size="utility">
          <a href={TELEGRAM_URL} target="_blank" rel="noreferrer">
            {CTA_LABEL}
          </a>
        </Button>
      </div>

      <Sheet>
        <SheetTrigger
          className="flex h-12 w-12 items-center justify-center rounded-secondary desktop:hidden"
          aria-label="Buka menu"
        >
          <Menu className="h-6 w-6 text-ink" />
        </SheetTrigger>
        <SheetContent>
          <SheetTitle>Menu</SheetTitle>
          <div className="flex flex-col gap-md">
            {LINKS.map((link) => (
              <SheetClose key={link.href}>
                <a
                  href={link.href}
                  className="flex min-h-xxl items-center text-nav-link text-ink no-underline"
                >
                  {link.label}
                </a>
              </SheetClose>
            ))}
          </div>
          <Button asChild variant="primary" className="w-full">
            <a href={TELEGRAM_URL} target="_blank" rel="noreferrer">
              {CTA_LABEL}
            </a>
          </Button>
        </SheetContent>
      </Sheet>
    </nav>
  );
}
