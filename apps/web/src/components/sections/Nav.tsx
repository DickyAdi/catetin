import { Menu } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Sheet, SheetClose, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { CTA_LABEL, TELEGRAM_URL } from "@/lib/constants";

const LINKS = [
  { href: "/#cara-kerja", label: "Cara Kerja" },
  { href: "/#harga", label: "Harga" },
  { href: "/#faq", label: "FAQ" },
];

export function Nav() {
  return (
    <nav className="mx-auto flex max-w-content items-center justify-between px-lg py-lg dark:bg-surface-dark">
      <Link to="/" className="flex items-center no-underline" aria-label="CatetIn — beranda">
        {/*
          Two <img>s swapped by the `dark:` variant rather than one src picked in
          JS: the CSS swap is already correct at first paint (the inline theme
          script in index.html has run), whereas a JS swap would flash the light
          mark until hydration.
        */}
        <img
          src="/assets/1_CatetIn_Light_Logo_Transparent.svg"
          alt="CatetIn"
          width={135}
          height={36}
          className="h-9 w-auto object-contain dark:hidden"
        />
        <img
          src="/assets/5_CatetIn_Dark_Logo_Transparent.svg"
          alt="CatetIn"
          width={135}
          height={36}
          className="hidden h-9 w-auto object-contain dark:block"
        />
      </Link>

      <div className="hidden items-center gap-xl desktop:flex">
        {LINKS.map((link) => (
          <a
            key={link.href}
            href={link.href}
            className="text-nav-link text-ink no-underline dark:text-on-dark"
          >
            {link.label}
          </a>
        ))}
      </div>

      <div className="hidden items-center gap-sm desktop:flex">
        <ThemeToggle />
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
          <Menu className="h-6 w-6 text-ink dark:text-on-dark" />
        </SheetTrigger>
        <SheetContent>
          <SheetTitle>Menu</SheetTitle>
          <div className="flex flex-col gap-md">
            {LINKS.map((link) => (
              <SheetClose key={link.href}>
                <a
                  href={link.href}
                  className="flex min-h-xxl items-center text-nav-link text-ink no-underline dark:text-on-dark"
                >
                  {link.label}
                </a>
              </SheetClose>
            ))}
          </div>
          <div className="flex items-center gap-sm">
            <ThemeToggle />
            <span className="text-body-small text-ink-muted dark:text-on-dark-muted">
              Mode gelap
            </span>
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
