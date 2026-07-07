import { redirect } from "next/navigation";

/** The app entry redirects into the platform console (which gates to /login). */
export default function Home() {
  redirect("/platform");
}
