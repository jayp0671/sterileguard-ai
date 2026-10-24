import { notFound } from "next/navigation";
import { env } from "@/lib/env";
import { StyleGallery } from "./style-gallery";

export const metadata = { title: "Style · SterileGuard AI" };

/** Every token and component, light and dark. Dev and staging only; SG-31 visual baseline. */
export default function StylePage() {
  if (env.appEnv === "production") notFound();
  return <StyleGallery />;
}
