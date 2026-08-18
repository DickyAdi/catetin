import * as React from "react";

import { cn } from "@/lib/utils";

interface TabsContextValue {
  value: string;
  setValue: (value: string) => void;
}

const TabsContext = React.createContext<TabsContextValue | null>(null);

function useTabsContext() {
  const ctx = React.useContext(TabsContext);
  if (!ctx) throw new Error("Tabs components must be used within <Tabs>");
  return ctx;
}

function Tabs({
  defaultValue,
  className,
  children,
}: {
  defaultValue: string;
  className?: string;
  children: React.ReactNode;
}) {
  const [value, setValue] = React.useState(defaultValue);
  return (
    <TabsContext.Provider value={{ value, setValue }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  );
}

function TabsList({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role="tablist"
      className={cn(
        "inline-flex items-center justify-center gap-xs rounded-secondary bg-divider-soft p-xxs",
        className,
      )}
      {...props}
    />
  );
}

function TabsTrigger({
  value,
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { value: string }) {
  const { value: active, setValue } = useTabsContext();
  return (
    <button
      role="tab"
      aria-selected={active === value}
      onClick={() => setValue(value)}
      className={cn(
        "inline-flex min-h-xxl items-center justify-center rounded-secondary px-lg py-sm text-button-utility text-ink-muted transition-colors",
        active === value && "bg-surface-white text-ink shadow-evidence",
        className,
      )}
      {...props}
    />
  );
}

function TabsContent({
  value,
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { value: string }) {
  const { value: active } = useTabsContext();
  if (active !== value) return null;
  return <div role="tabpanel" className={cn("mt-lg", className)} {...props} />;
}

export { Tabs, TabsList, TabsTrigger, TabsContent };
