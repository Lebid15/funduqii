"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  Image as ImageIcon,
  ImagePlus,
  Trash2,
  Upload,
} from "lucide-react";

import {
  Card,
  ConfirmDialog,
  EmptyState,
  Icon,
  IconButton,
  SectionHeader,
  useToast,
} from "@/components/ui";
import { deleteMedia, listMedia, updateMedia, uploadMedia } from "@/lib/api/hotel";
import { messageForError } from "@/lib/api/errors";
import type { HotelMedia, MediaKind } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

const ACCEPT = "image/png,image/jpeg,image/webp";

/** Manages the hotel's logo, cover and gallery. Uploads/deletes are separate
 * from text settings, so saving settings never touches images. */
export function HotelMediaSection({ disabled }: { disabled: boolean }) {
  const { t } = useI18n();
  const { notify } = useToast();
  const [media, setMedia] = useState<HotelMedia[]>([]);
  const [busyKind, setBusyKind] = useState<MediaKind | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<HotelMedia | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setMedia(await listMedia());
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }, [t, notify]);

  useEffect(() => {
    load();
  }, [load]);

  const logo = media.find((m) => m.kind === "logo" && m.is_active) ?? null;
  const cover = media.find((m) => m.kind === "cover" && m.is_active) ?? null;
  const gallery = media
    .filter((m) => m.kind === "gallery")
    .sort((a, b) => a.sort_order - b.sort_order);

  async function handleUpload(kind: MediaKind, file: File) {
    setBusyKind(kind);
    try {
      await uploadMedia(kind, file);
      notify(t.hotel.settings.saved);
      await load();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setBusyKind(null);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    try {
      await deleteMedia(deleteTarget.id);
      notify(t.hotel.settings.saved);
      setDeleteTarget(null);
      await load();
    } catch (err) {
      notify(messageForError(err, t), "error");
      setDeleteTarget(null);
    } finally {
      setDeleteBusy(false);
    }
  }

  async function move(item: HotelMedia, direction: 1 | -1) {
    const index = gallery.findIndex((g) => g.id === item.id);
    const swapWith = gallery[index + direction];
    if (!swapWith) return;
    try {
      await updateMedia(item.id, { sort_order: swapWith.sort_order });
      await updateMedia(swapWith.id, { sort_order: item.sort_order });
      await load();
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  return (
    <Card className="settings-section">
      <SectionHeader
        title={t.hotel.settings.sectionMedia}
        description={t.hotel.settings.sectionMediaDesc}
        icon={ImagePlus}
      />

      <div className="media-slots">
        <ImageSlot
          label={t.hotel.settings.logo}
          hint={t.hotel.settings.logoHint}
          media={logo}
          shape="logo"
          uploading={busyKind === "logo"}
          disabled={disabled}
          onFile={(file) => handleUpload("logo", file)}
        />
        <ImageSlot
          label={t.hotel.settings.cover}
          hint={t.hotel.settings.coverHint}
          media={cover}
          shape="cover"
          uploading={busyKind === "cover"}
          disabled={disabled}
          onFile={(file) => handleUpload("cover", file)}
        />
      </div>

      <div className="media-gallery">
        <div className="media-slot__head">
          <span className="media-slot__title">{t.hotel.settings.gallery}</span>
          <span className="field__hint">{t.hotel.settings.galleryHint}</span>
        </div>
        <UploadButton
          label={t.hotel.settings.upload}
          uploadingLabel={t.hotel.settings.uploading}
          uploading={busyKind === "gallery"}
          disabled={disabled}
          onFile={(file) => handleUpload("gallery", file)}
        />
        {gallery.length === 0 ? (
          <EmptyState
            title={t.hotel.settings.galleryEmpty}
            hint={t.hotel.settings.galleryEmptyHint}
            icon={ImageIcon}
          />
        ) : (
          <div className="gallery-grid">
            {gallery.map((item, index) => (
              <figure className="gallery-item" key={item.id}>
                {item.url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={item.url} alt={item.alt_text || t.hotel.settings.gallery} />
                ) : null}
                <figcaption className="gallery-item__bar">
                  <IconButton
                    label={t.hotel.settings.moveUp}
                    icon={ArrowUp}
                    disabled={disabled || index === 0}
                    onClick={() => move(item, -1)}
                  />
                  <IconButton
                    label={t.hotel.settings.moveDown}
                    icon={ArrowDown}
                    disabled={disabled || index === gallery.length - 1}
                    onClick={() => move(item, 1)}
                  />
                  <IconButton
                    label={t.hotel.settings.remove}
                    icon={Trash2}
                    disabled={disabled}
                    onClick={() => setDeleteTarget(item)}
                  />
                </figcaption>
              </figure>
            ))}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        title={t.hotel.settings.deleteImageTitle}
        body={t.hotel.settings.deleteImageBody}
        confirmLabel={t.hotel.settings.remove}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        tone="danger"
        busy={deleteBusy}
        onConfirm={confirmDelete}
        onClose={() => setDeleteTarget(null)}
      />
    </Card>
  );
}

function ImageSlot({
  label,
  hint,
  media,
  shape,
  uploading,
  disabled,
  onFile,
}: {
  label: string;
  hint: string;
  media: HotelMedia | null;
  shape: "logo" | "cover";
  uploading: boolean;
  disabled: boolean;
  onFile: (file: File) => void;
}) {
  const { t } = useI18n();
  return (
    <div className="media-slot">
      <div className="media-slot__head">
        <span className="media-slot__title">{label}</span>
        <span className="field__hint">{hint}</span>
      </div>
      <div className={`media-preview media-preview--${shape}`}>
        {media?.url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={media.url} alt={media.alt_text || label} />
        ) : (
          <span className="media-preview__empty">
            <Icon icon={ImageIcon} size="lg" />
            <span>{t.hotel.settings.noImage}</span>
          </span>
        )}
      </div>
      <UploadButton
        label={media ? t.hotel.settings.replace : t.hotel.settings.upload}
        uploadingLabel={t.hotel.settings.uploading}
        uploading={uploading}
        disabled={disabled}
        onFile={onFile}
      />
    </div>
  );
}

function UploadButton({
  label,
  uploadingLabel,
  uploading,
  disabled,
  onFile,
}: {
  label: string;
  uploadingLabel: string;
  uploading: boolean;
  disabled: boolean;
  onFile: (file: File) => void;
}) {
  return (
    <label
      className="btn btn--secondary btn--sm media-upload"
      data-disabled={disabled || uploading || undefined}
    >
      <Icon icon={Upload} size="sm" />
      {uploading ? uploadingLabel : label}
      <input
        type="file"
        accept={ACCEPT}
        hidden
        disabled={disabled || uploading}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onFile(file);
          event.target.value = "";
        }}
      />
    </label>
  );
}
