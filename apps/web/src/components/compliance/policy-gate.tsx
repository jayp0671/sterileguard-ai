"use client";

import type { components } from "@sg/contracts";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { accessToken } from "@/hooks/use-me";
import { api } from "@/lib/api";

type Policies = components["schemas"]["PoliciesOut"];
const NAMES = { terms: "Terms of Use", privacy: "Privacy Policy" } as const;

/** After sign-in, the current Terms and Privacy versions must be accepted (SG-25). */
export function PolicyGate() {
  const qc = useQueryClient();
  const [checked, setChecked] = useState(false);
  const q = useQuery({
    queryKey: ["policies"],
    retry: false,
    queryFn: async (): Promise<Policies> => {
      const { data } = await api(accessToken).GET("/v1/me/policies");
      if (!data) throw new Error("empty");
      return data;
    },
  });
  const accept = useMutation({
    mutationFn: async (pending: Policies["policies"]) => {
      let last: Policies | undefined;
      for (const p of pending) {
        const { data } = await api(accessToken).POST("/v1/me/policies", {
          body: { policy: p.policy, version: p.version },
        });
        last = data;
      }
      return last;
    },
    onSuccess: (data) => {
      if (data) qc.setQueryData(["policies"], data);
    },
  });
  if (!q.data || q.data.all_accepted) return null;
  const pending = q.data.policies.filter((p) => !p.accepted);
  return (
    <PolicyDialog
      pending={pending}
      checked={checked}
      onCheck={setChecked}
      busy={accept.isPending}
      onAccept={() => accept.mutate(pending)}
    />
  );
}

export function PolicyDialog({
  pending,
  checked,
  onCheck,
  busy,
  onAccept,
}: {
  pending: Policies["policies"];
  checked: boolean;
  onCheck: (v: boolean) => void;
  busy: boolean;
  onAccept: () => void;
}) {
  return (
    <Dialog open>
      <DialogContent
        onEscapeKeyDown={(e) => e.preventDefault()}
        onPointerDownOutside={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
        className="[&>button]:hidden"
      >
        <DialogHeader>
          <DialogTitle>Please review our policies</DialogTitle>
          <DialogDescription>
            SterileGuard AI is an academic prototype for decision support. Before you continue, read
            and accept:
          </DialogDescription>
        </DialogHeader>
        <ul className="flex flex-col gap-1 text-sm">
          {pending.map((p) => (
            <li key={p.policy}>
              <a
                href={`/trust/${p.policy}`}
                target="_blank"
                rel="noreferrer"
                className="underline underline-offset-4"
              >
                {NAMES[p.policy]}
              </a>{" "}
              <span className="text-muted-foreground">(version {p.version})</span>
            </li>
          ))}
        </ul>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-0.5 size-4"
            checked={checked}
            onChange={(e) => onCheck(e.target.checked)}
          />
          I have read and accept these policies, and I will not enter patient information.
        </label>
        <Button className="min-h-11" disabled={!checked || busy} onClick={onAccept}>
          Accept and continue
        </Button>
      </DialogContent>
    </Dialog>
  );
}
