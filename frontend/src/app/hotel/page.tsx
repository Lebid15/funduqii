import { redirect } from "next/navigation";

/** The hotel console entry points at settings (the only Phase 4 hotel screen). */
export default function HotelHome() {
  redirect("/hotel/settings");
}
