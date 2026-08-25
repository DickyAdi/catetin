import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-secondary px-sm py-xxs text-button-utility font-semibold",
  {
    variants: {
      variant: {
        default: "bg-primary-soft text-primary dark:bg-surface-dark dark:text-primary-on-dark",
        outline:
          "border border-hairline text-ink-muted dark:border-surface-dark-soft dark:text-on-dark-muted",
        placeholder: "bg-divider-soft text-ink-faint dark:bg-surface-dark dark:text-on-dark-muted",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
