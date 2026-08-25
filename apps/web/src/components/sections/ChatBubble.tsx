import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function PhoneFrame({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "mx-auto w-full max-w-[380px] rounded-[24px] bg-surface-white p-sm shadow-evidence dark:bg-surface-dark-soft",
        className,
      )}
    >
      <div className="flex flex-col gap-sm rounded-card bg-canvas p-md dark:bg-surface-dark">
        {children}
      </div>
    </div>
  );
}

export function UserBubble({ children }: { children: ReactNode }) {
  return (
    <div className="max-w-[80%] self-end rounded-[14px] bg-surface-white px-md py-sm text-body shadow-evidence dark:bg-surface-dark-soft dark:text-on-dark">
      {children}
    </div>
  );
}

// `primary/25` is the dark-theme stand-in for `primary-soft`: the palette has no
// dark tint token, and a flat surface-dark-soft would leave the bot bubble
// indistinguishable from the user bubble above it.
export function BotBubble({ children }: { children: ReactNode }) {
  return (
    <div className="max-w-[85%] self-start rounded-[14px] bg-primary-soft px-md py-sm text-body dark:bg-primary/25 dark:text-on-dark">
      {children}
    </div>
  );
}

export function Money({ amount, sign }: { amount: string; sign: "+" | "-" }) {
  return (
    <span
      className={cn(
        "tabular-money font-bold",
        sign === "+" ? "text-profit" : "text-expense",
      )}
    >
      {sign}Rp {amount}
    </span>
  );
}
