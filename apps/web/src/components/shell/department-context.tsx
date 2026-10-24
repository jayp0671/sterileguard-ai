"use client";

import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";
import type { Me } from "@/hooks/use-me";
import type { AppRole } from "@/lib/nav";

const STORAGE_KEY = "sg.department";

type DepartmentState = {
  me: Me | undefined;
  departmentId: string | undefined;
  departmentName: string | undefined;
  roles: AppRole[];
  setDepartmentId: (id: string) => void;
};

const Ctx = createContext<DepartmentState | null>(null);

/** The department the user is working in, remembered per browser. Pages read it via useDepartment. */
export function DepartmentProvider({ me, children }: { me: Me | undefined; children: ReactNode }) {
  const [chosen, setChosen] = useState<string | undefined>(undefined);
  useEffect(() => {
    try {
      setChosen(window.localStorage.getItem(STORAGE_KEY) ?? undefined);
    } catch {
      // storage blocked: fall back to the first membership
    }
  }, []);
  const value = useMemo<DepartmentState>(() => {
    const memberships = me?.memberships ?? [];
    const current = memberships.find((m) => m.department_id === chosen) ?? memberships[0];
    return {
      me,
      departmentId: current?.department_id,
      departmentName: current?.department_name,
      roles: current?.roles ?? [],
      setDepartmentId: (id: string) => {
        setChosen(id);
        try {
          window.localStorage.setItem(STORAGE_KEY, id);
        } catch {
          // ignore
        }
      },
    };
  }, [me, chosen]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useDepartment(): DepartmentState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useDepartment must be used inside the app shell");
  return ctx;
}
