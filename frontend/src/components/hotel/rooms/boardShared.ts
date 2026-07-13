import {
  Accessibility,
  Archive,
  Ban,
  Bath,
  BedDouble,
  BedSingle,
  Brush,
  Briefcase,
  CalendarClock,
  CalendarPlus,
  CheckCircle2,
  Cigarette,
  CigaretteOff,
  Coffee,
  ConciergeBell,
  Dot,
  DoorOpen,
  Eye,
  Fence,
  FileText,
  Flame,
  Lock,
  LogIn,
  LogOut,
  Mountain,
  Refrigerator,
  Snowflake,
  Sparkles,
  Tv,
  UserCheck,
  Users,
  Utensils,
  VolumeX,
  Waves,
  Wifi,
  Wind,
  Wine,
  Wrench,
  type LucideIcon,
} from "lucide-react";

import type { BadgeTone } from "@/components/ui";
import type {
  RoomBoardRoom,
  RoomOccupancyStatus,
  RoomStatus,
} from "@/lib/api/types";
import type { Dictionary } from "@/lib/i18n/dictionaries";

/** OCCUPANCY axis badge (free / occupied / reserved) — tone + icon, never
 * colour alone (WCAG). Independent from the operational status. */
export function occupancyTone(status: RoomOccupancyStatus): BadgeTone {
  switch (status) {
    case "occupied":
      return "info";
    case "reserved":
      return "warning";
    default:
      return "success"; // free
  }
}

export function occupancyIcon(status: RoomOccupancyStatus): LucideIcon {
  switch (status) {
    case "occupied":
      return UserCheck;
    case "reserved":
      return CalendarClock;
    default:
      return DoorOpen; // free
  }
}

/** OPERATIONAL-status axis badge (available / dirty / cleaning / maintenance /
 * out_of_service / archived) — tone + icon, never colour alone (WCAG). */
export function operationalTone(status: RoomStatus): BadgeTone {
  switch (status) {
    case "available":
      return "success";
    case "dirty":
      return "warning";
    case "cleaning":
      return "info";
    case "maintenance":
      return "danger";
    case "out_of_service":
      return "neutral";
    default:
      return "neutral"; // archived
  }
}

export function operationalIcon(status: RoomStatus): LucideIcon {
  switch (status) {
    case "available":
      return CheckCircle2;
    case "dirty":
      return Sparkles;
    case "cleaning":
      return Brush;
    case "maintenance":
      return Wrench;
    case "out_of_service":
      return Ban;
    default:
      return Archive; // archived
  }
}

/** Amenity-key → unified lucide icon. Icons ACCOMPANY the translated label
 * (they are never the sole conveyor of meaning); unknown keys fall back to a
 * neutral dot. Kept beside the operational icons so the whole rooms section
 * draws from one consistent set. */
const AMENITY_ICON: Record<string, LucideIcon> = {
  ac: Snowflake,
  wifi: Wifi,
  tv: Tv,
  private_bathroom: Bath,
  fridge: Refrigerator,
  balcony: Fence,
  view: Mountain,
  minibar: Wine,
  safe: Lock,
  desk: Briefcase,
  heating: Flame,
  kettle: Coffee,
  hair_dryer: Wind,
  room_service: ConciergeBell,
  single_bed: BedSingle,
  double_bed: BedDouble,
  twin_beds: BedDouble,
  jacuzzi: Waves,
  kitchenette: Utensils,
  soundproof: VolumeX,
  no_smoking: CigaretteOff,
  smoking: Cigarette,
  family_friendly: Users,
  accessible: Accessibility,
};

export function amenityIcon(key: string): LucideIcon {
  return AMENITY_ICON[key] ?? Dot;
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
          key: "occupancyDetails",
          label: b.occupancyDetails,
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
