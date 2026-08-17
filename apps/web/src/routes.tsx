import type { RouteRecord } from "vite-react-ssg";

import { CaraKerja } from "@/pages/CaraKerja";
import { KebijakanPrivasi } from "@/pages/KebijakanPrivasi";
import { Landing } from "@/pages/Landing";

export const routes: RouteRecord[] = [
  {
    path: "/",
    element: <Landing />,
    entry: "src/pages/Landing.tsx",
  },
  {
    path: "/cara-kerja",
    element: <CaraKerja />,
    entry: "src/pages/CaraKerja.tsx",
  },
  {
    path: "/kebijakan-privasi",
    element: <KebijakanPrivasi />,
    entry: "src/pages/KebijakanPrivasi.tsx",
  },
];
