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
        "mx-auto w-full max-w-[380px] rounded-[24px] bg-surface-white p-sm shadow-evidence",
        className,
      )}
    >
      <div className="flex flex-col gap-sm rounded-card bg-canvas p-md">{children}</div>
    </div>
  );
}

export function UserBubble({ children }: { children: ReactNode }) {
  return (
    <div className="max-w-[80%] self-end rounded-[14px] bg-surface-white px-md py-sm text-body shadow-evidence">
      {children}
    </div>
  );
}

export function BotBubble({ children }: { children: ReactNode }) {
  return (
    <div className="max-w-[85%] self-start rounded-[14px] bg-primary-soft px-md py-sm text-body">
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
