import * as React from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";

// Plain state-driven drawer instead of Radix Dialog — the focus-trap /
// scroll-lock / portal machinery there cost ~20KB gzip for a single mobile
// hamburger menu, which blew the performance budget.
interface SheetContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
}

const SheetContext = React.createContext<SheetContextValue | null>(null);

function useSheetContext() {
  const ctx = React.useContext(SheetContext);
  if (!ctx) throw new Error("Sheet components must be used within <Sheet>");
  return ctx;
}

function Sheet({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  return <SheetContext.Provider value={{ open, setOpen }}>{children}</SheetContext.Provider>;
}

const SheetTrigger = React.forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement>
>(({ onClick, ...props }, ref) => {
  const { setOpen } = useSheetContext();
  return (
    <button
      ref={ref}
      onClick={(event) => {
        onClick?.(event);
        setOpen(true);
      }}
      {...props}
    />
  );
});
SheetTrigger.displayName = "SheetTrigger";

// Clones its single child (always an <a> or similar) and wires up close-on-click —
// a hand-rolled equivalent of Radix's Slot, scoped to this one use case.
function SheetClose({ children }: { children: React.ReactElement<{ onClick?: (e: React.MouseEvent) => void }> }) {
  const { setOpen } = useSheetContext();
  return React.cloneElement(children, {
    onClick: (event: React.MouseEvent) => {
      children.props.onClick?.(event);
      setOpen(false);
    },
  });
}

function SheetContent({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  const { open, setOpen } = useSheetContext();
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);

  if (!mounted || !open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50">
      <div
        className="absolute inset-0 bg-ink/40"
        onClick={() => setOpen(false)}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          "absolute inset-y-0 right-0 flex h-full w-4/5 max-w-sm flex-col gap-lg border-l border-hairline bg-surface-white p-lg shadow-evidence",
          className,
        )}
      >
        {children}
        <button
          onClick={() => setOpen(false)}
          className="absolute right-lg top-lg flex h-12 w-12 items-center justify-center rounded-secondary text-ink-muted hover:bg-divider-soft"
        >
          <X className="h-6 w-6" />
          <span className="sr-only">Tutup</span>
        </button>
      </div>
    </div>,
    document.body,
  );
}

function SheetTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={cn("text-body-strong text-ink", className)} {...props} />;
}

export { Sheet, SheetTrigger, SheetClose, SheetContent, SheetTitle };
