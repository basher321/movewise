"use client";

import { useEffect, useId, useRef } from "react";
import type { CSSProperties, MouseEvent, ReactNode, SyntheticEvent } from "react";

type ModalProps = {
  open: boolean;
  // Shown as the heading; a dialog without a heading (the invoice) passes label instead.
  title?: string;
  label?: string;
  onClose: () => void;
  // The section colour (--a) inside the dialog, as the reference sets it.
  accent?: string;
  // The reference xd(..., wide): a wider dialog for long forms.
  wide?: boolean;
  children?: ReactNode;
};

export default function Modal({ open, title, label, onClose, accent, wide, children }: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  // Opens the dialog; on close or unmount, focus returns to the element that opened it.
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog || !open) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (!dialog.open) dialog.showModal();
    return () => {
      if (dialog.open) dialog.close();
      if (opener?.isConnected) opener.focus();
    };
  }, [open]);

  // Escape fires "cancel"; let the parent decide by closing through onClose.
  function handleCancel(e: SyntheticEvent<HTMLDialogElement>) {
    e.preventDefault();
    onClose();
  }

  // A click outside the box lands on the dialog element itself (its backdrop).
  function handleClick(e: MouseEvent<HTMLDialogElement>) {
    if (e.target !== e.currentTarget) return;
    const box = e.currentTarget.getBoundingClientRect();
    const inside = e.clientX >= box.left && e.clientX <= box.right && e.clientY >= box.top && e.clientY <= box.bottom;
    if (!inside) onClose();
  }

  const style: CSSProperties | undefined =
    accent || wide
      ? ({ ...(accent ? { "--a": accent } : {}), ...(wide ? { width: "min(680px, calc(100% - 32px))", maxHeight: "92vh", overflow: "auto" } : {}) } as CSSProperties)
      : undefined;

  return (
    <dialog
      ref={ref}
      aria-labelledby={title ? titleId : undefined}
      aria-label={title ? undefined : label}
      onCancel={handleCancel}
      onClick={handleClick}
      style={style}
    >
      <button className="x" type="button" aria-label="Close" onClick={onClose}>
        ×
      </button>
      {title ? <h3 id={titleId}>{title}</h3> : null}
      {children}
    </dialog>
  );
}
