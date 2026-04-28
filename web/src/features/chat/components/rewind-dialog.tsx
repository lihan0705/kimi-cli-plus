import type { FileDiffEntry } from "@/hooks/useCheckpoints";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Undo2Icon, PlusIcon, MinusIcon, TrashIcon, FileIcon } from "lucide-react";

type RewindDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  files: FileDiffEntry[];
  onRewindConversation: () => void;
  onRewindAndRestore: () => void;
  isLoading?: boolean;
};

const statusConfig: Record<string, { label: string; icon: typeof PlusIcon; className: string }> = {
  A: { label: "Added", icon: PlusIcon, className: "text-green-500" },
  M: { label: "Modified", icon: MinusIcon, className: "text-yellow-500" },
  D: { label: "Deleted", icon: TrashIcon, className: "text-red-500" },
};

export function RewindDialog({
  open,
  onOpenChange,
  files,
  onRewindConversation,
  onRewindAndRestore,
  isLoading = false,
}: RewindDialogProps) {
  const fileCount = files.length;
  const fileLabel =
    fileCount === 0
      ? "no file changes"
      : `${fileCount} file${fileCount !== 1 ? "s" : ""} changed`;

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent size="sm">
        <AlertDialogHeader>
          <AlertDialogTitle>Rewind to This Point</AlertDialogTitle>
          <AlertDialogDescription>
            Messages after this point will be removed from the conversation.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-2">
          <Button
            variant="outline"
            className="w-full justify-start text-sm h-auto py-2.5"
            onClick={onRewindConversation}
            disabled={isLoading}
          >
            <Undo2Icon className="size-3.5 mr-2 shrink-0" />
            <span className="text-left">
              <span className="font-medium">Rewind conversation only</span>
              <span className="block text-xs text-muted-foreground mt-0.5">
                Files remain unchanged
              </span>
            </span>
          </Button>

          <Button
            variant="outline"
            className="w-full justify-start text-sm h-auto py-2.5"
            onClick={onRewindAndRestore}
            disabled={isLoading}
          >
            <Undo2Icon className="size-3.5 mr-2 shrink-0" />
            <span className="text-left">
              <span className="font-medium">Rewind + restore files</span>
              <span className="block text-xs text-muted-foreground mt-0.5">
                [{fileLabel}]
              </span>
            </span>
          </Button>

          {fileCount > 0 && (
            <ul className="max-h-36 overflow-y-auto space-y-0.5 pl-2 border-l-2 border-muted ml-1">
              {files.map((file) => {
                const config = statusConfig[file.status] ?? {
                  label: file.status,
                  icon: FileIcon,
                  className: "text-muted-foreground",
                };
                const Icon = config.icon;
                return (
                  <li
                    key={`${file.status}-${file.path}`}
                    className="flex items-center gap-1.5 text-xs font-mono py-0.5"
                  >
                    <Icon className={`size-2.5 shrink-0 ${config.className}`} />
                    <span className="text-muted-foreground w-14 shrink-0 text-[10px]">
                      {config.label}
                    </span>
                    <span className="truncate">{file.path}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel disabled={isLoading}>
            {isLoading ? "Rewinding..." : "Cancel"}
          </AlertDialogCancel>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
