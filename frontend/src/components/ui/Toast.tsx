"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { cx } from "@/lib/utils";

type ToastTone = "success" | "error";

interface ToastItem {
  id: number;
  tone: ToastTone;
  message: string;
}

interface ToastApi {
  notify: (message: string, tone?: ToastTone) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

/** Provides an app-wide toast queue. Messages are translated by the caller. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  // Auto-dismiss timers still in flight. They are tracked so they can be
  // CLEARED on unmount: an un-cleared timer fires after the tree is gone and
  // calls setState on an unmounted provider. In the app that is a wasted update;
  // under jsdom it throws `ReferenceError: window is not defined` AFTER the test
  // environment is torn down, which the runner reports as an unhandled error and
  // turns into a non-zero exit code even though every test passed — a failure
  // mode that reads as a false green when output is piped.
  const timers = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());

  const notify = useCallback((message: string, tone: ToastTone = "success") => {
    const id = nextId.current++;
    setToasts((current) => [...current, { id, tone, message }]);
    const timer = setTimeout(() => {
      timers.current.delete(timer);
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }, 4000);
    timers.current.add(timer);
  }, []);

  useEffect(() => {
    // Capture the Set itself: reading `timers.current` inside the cleanup would
    // read it at unmount time, which is the same object here but is the pattern
    // the exhaustive-deps rule warns about.
    const pending = timers.current;
    return () => {
      pending.forEach(clearTimeout);
      pending.clear();
    };
  }, []);

  return (
    <ToastContext.Provider value={{ notify }}>
      {children}
      <div className="toast-region" aria-live="polite" aria-atomic="false">
        {toasts.map((toast) => (
          <div key={toast.id} className={cx("toast", `toast--${toast.tone}`)}>
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const value = useContext(ToastContext);
  if (value === null) {
    throw new Error("useToast must be used within a ToastProvider.");
  }
  return value;
}
