import {
  Brush,
  CalendarPlus,
  DoorOpen,
  Eye,
  FileText,
  LogIn,
  LogOut,
  Wrench,
  type LucideIcon,
} from "lucide-react";

import type { BadgeTone } from "@/components/ui";
import type { RoomBoardRoom, RoomDisplayStatus } from "@/lib/api/types";
import type { Dictionary } from "@/lib/i18n/dictionaries";

/** Owner palette: calm, meaningful tones per DISPLAY status. */
export function displayStatusTone(status: RoomDisplayStatus): BadgeTone {
  switch (status) {
    case "available":
      return "success";
    case "occupied":
      return "info";
    case "reserved":
      return "warning";
    case "dirty":
      return "warning";
    case "cleaning":
      return "info";
    case "maintenance":
      return "danger";
    default:
      return "neutral"; // out_of_service / archived
  }
}

export interface RoomLinkAction {
  key: string;
  label: string;
  href: string;
  icon: LucideIcon;
}

/**
 * The status-appropriate LINK actions for one room (owner spec), already
 * filtered by Phase 11 permissions (same any-of `can` as the sidebar).
 * Entity-scoped operations (check-in/out, folio) land on their existing
 * selection surfaces; create operations deep-link the existing forms via
 * `?action=new&room=` (consumed once by useQuickAction). Status change and
 * details are handled by the callers (modal / drawer), not links.
 */
export function buildRoomLinks(
  room: RoomBoardRoom,
  t: Dictionary,
  can: (...codes: string[]) => boolean,
): RoomLinkAction[] {
  const b = t.rooms.board;
  const links: RoomLinkAction[] = [];

  switch (room.display_status) {
    case "available":
      if (can("reservations.view")) {
        links.push({
          key: "newReservation",
          label: b.newReservation,
          icon: CalendarPlus,
          href: `/hotel/reservations?tab=reservations&action=new&room=${room.id}&room_type=${room.room_type}`,
        });
      }
      break;
    case "reserved":
      if (can("reservations.view") && room.next_reservation) {
        links.push({
          key: "viewReservation",
          label: b.viewReservation,
          icon: Eye,
          href: `/hotel/reservations?tab=reservations&action=find&q=${encodeURIComponent(room.next_reservation.reservation_number)}`,
        });
      }
      if (can("stays.view")) {
        links.push({
          key: "checkIn",
          label: b.checkIn,
          icon: LogIn,
          href: "/hotel/front-desk?tab=arrivals",
        });
      }
      break;
    case "occupied":
      if (can("stays.view")) {
        links.push({
          key: "viewStay",
          label: b.viewStay,
          icon: DoorOpen,
          href: "/hotel/front-desk?tab=current",
        });
      }
      if (can("finance.view")) {
        links.push({
          key: "guestFolio",
          label: b.guestFolio,
          icon: FileText,
          href: "/hotel/finance?tab=folios",
        });
      }
      if (can("stays.view")) {
        links.push({
          key: "checkOut",
          label: b.checkOut,
          icon: LogOut,
          href: "/hotel/front-desk?tab=departures",
        });
      }
      break;
    case "dirty":
      if (can("housekeeping.view")) {
        links.push({
          key: "createCleaningTask",
          label: b.createCleaningTask,
          icon: Brush,
          href: `/hotel/operations?tab=housekeeping&action=new&room=${room.id}`,
        });
      }
      break;
    case "cleaning":
      if (can("housekeeping.view")) {
        links.push({
          key: "viewCleaningTask",
          label: b.viewCleaningTask,
          icon: Brush,
          href: "/hotel/operations?tab=housekeeping",
        });
      }
      break;
    case "maintenance":
      if (can("maintenance.view")) {
        links.push({
          key: "viewMaintenance",
          label: b.viewMaintenance,
          icon: Wrench,
          href: "/hotel/operations?tab=maintenance",
        });
        links.push({
          key: "createMaintenance",
          label: b.createMaintenance,
          icon: Wrench,
          href: `/hotel/operations?tab=maintenance&action=new&room=${room.id}`,
        });
      }
      break;
    default:
      break; // out_of_service / archived: details + status change only
  }
  return links;
}
