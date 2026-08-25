import * as React from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

// Native <details>/<summary> instead of Radix — free accessibility and
// disclosure state from the browser, at zero JS cost.
const Accordion = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => <div ref={ref} className={className} {...props} />,
);
Accordion.displayName = "Accordion";

const AccordionItem = React.forwardRef<
  HTMLDetailsElement,
  React.DetailsHTMLAttributes<HTMLDetailsElement>
>(({ className, ...props }, ref) => (
  <details
    ref={ref}
    className={cn("group border-b border-hairline dark:border-surface-dark-soft", className)}
    {...props}
  />
));
AccordionItem.displayName = "AccordionItem";

const AccordionTrigger = React.forwardRef<
  HTMLElement,
  React.HTMLAttributes<HTMLElement>
>(({ className, children, ...props }, ref) => (
  <summary
    ref={ref as React.Ref<HTMLElement>}
    className={cn(
      "flex min-h-xxl cursor-pointer list-none items-center justify-between gap-md py-lg text-body-strong text-ink dark:text-on-dark [&::-webkit-details-marker]:hidden",
      className,
    )}
    {...props}
  >
    {children}
    <ChevronDown className="h-5 w-5 shrink-0 text-ink-muted transition-transform duration-200 group-open:rotate-180 dark:text-on-dark-muted" />
  </summary>
));
AccordionTrigger.displayName = "AccordionTrigger";

const AccordionContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, children, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("pb-lg text-body-small text-ink-muted dark:text-on-dark-muted", className)}
    {...props}
  >
    {children}
  </div>
));
AccordionContent.displayName = "AccordionContent";

export { Accordion, AccordionItem, AccordionTrigger, AccordionContent };
