import * as React from "react";
import { Moon, Sun } from "lucide-react";

import { cn } from "@/lib/utils";

const STORAGE_KEY = "catetin-theme";

// The initial theme is applied by the inline script in index.html (before first
// paint, to avoid FOUC on this prerendered site). This component owns the
// *toggle*, so on mount it reads back whatever that script decided rather than
// re-deriving it. Initial state is `false` so the prerendered markup and the
// first client render agree — the effect corrects it immediately after.
export function ThemeToggle({ className }: { className?: string }) {
  const [isDark, setIsDark] = React.useState(false);

  React.useEffect(() => {
    setIsDark(document.documentElement.classList.contains("dark"));
  }, []);

  function toggle() {
    const next = !isDark;
    setIsDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem(STORAGE_KEY, next ? "dark" : "light");
    } catch {
      /* storage blocked: the toggle still works for this page view */
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={isDark ? "Aktifkan mode terang" : "Aktifkan mode gelap"}
      aria-pressed={isDark}
      className={cn(
        "flex h-12 w-12 shrink-0 items-center justify-center rounded-secondary text-ink transition-colors hover:bg-divider-soft dark:text-on-dark dark:hover:bg-surface-dark-soft",
        className,
      )}
    >
      {isDark ? <Sun className="h-6 w-6" /> : <Moon className="h-6 w-6" />}
    </button>
  );
}
