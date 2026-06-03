import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  Loader2,
  MessageSquare,
  Send,
  Trash2,
  Upload,
} from "lucide-react"
import { useRef, useState } from "react"
import { toast } from "sonner"
import { type DocumentPublic, DocumentsService } from "@/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export const Route = createFileRoute("/_layout/documents")({
  component: DocumentsPage,
})

interface Message {
  role: "user" | "assistant"
  text: string
}

function DocumentsPage() {
  const queryClient = useQueryClient()
  const [selectedDoc, setSelectedDoc] = useState<DocumentPublic | null>(null)
  const [uploadTitle, setUploadTitle] = useState("")
  const [file, setFile] = useState<File | null>(null)
  const [chatQuery, setChatQuery] = useState("")
  const [chatMessages, setChatMessages] = useState<Message[]>([])
  const [isChatLoading, setIsChatLoading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 1. Fetch Documents Query
  const { data: docsData, isLoading: isDocsLoading } = useQuery({
    queryKey: ["documents"],
    queryFn: () => DocumentsService.readDocuments(),
  })

  // 2. Upload Document Mutation
  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("No file selected")
      return DocumentsService.uploadDocument({
        formData: {
          file: file,
          title: uploadTitle || undefined,
        },
      })
    },
    onSuccess: (data) => {
      toast.success("Document uploaded & reviewed successfully!")
      setFile(null)
      setUploadTitle("")
      if (fileInputRef.current) fileInputRef.current.value = ""
      queryClient.invalidateQueries({ queryKey: ["documents"] })
      setSelectedDoc(data)
      setChatMessages([])
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to upload document")
    },
  })

  // 3. Delete Document Mutation
  const deleteMutation = useMutation({
    mutationFn: (docId: string) => DocumentsService.deleteDocument({ docId }),
    onSuccess: () => {
      toast.success("Document deleted successfully")
      if (selectedDoc) setSelectedDoc(null)
      queryClient.invalidateQueries({ queryKey: ["documents"] })
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to delete document")
    },
  })

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0])
    }
  }

  const handleUploadSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    uploadMutation.mutate()
  }

  // 4. Send Chat Query to Ollama Chatbot Agent
  const handleSendChat = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!chatQuery.trim() || !selectedDoc) return

    const userMessage: Message = { role: "user", text: chatQuery }
    setChatMessages((prev) => [...prev, userMessage])
    setChatQuery("")
    setIsChatLoading(true)

    try {
      const response = await DocumentsService.chatAboutDocument({
        docId: selectedDoc.id,
        requestBody: { query: userMessage.text },
      })
      const botMessage: Message = { role: "assistant", text: response.message }
      setChatMessages((prev) => [...prev, botMessage])
    } catch (err: any) {
      toast.error(err.message || "Chat failed")
      const errorMessage: Message = {
        role: "assistant",
        text: `Error: ${err.message || "Could not communicate with Ollama Agent"}`,
      }
      setChatMessages((prev) => [...prev, errorMessage])
    } finally {
      setIsChatLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-6 md:flex-row min-h-[calc(100vh-10rem)]">
      {/* LEFT COLUMN: List of Documents */}
      <div className="w-full md:w-80 border rounded-lg p-4 flex flex-col gap-4 bg-card shrink-0">
        <h2 className="text-xl font-bold flex items-center gap-2">
          <FileText className="h-5 w-5" />
          My Documents
        </h2>

        {/* Upload Form */}
        <form
          onSubmit={handleUploadSubmit}
          className="flex flex-col gap-3 border-b pb-4"
        >
          <Input
            type="text"
            placeholder="Custom Document Title"
            value={uploadTitle}
            onChange={(e) => setUploadTitle(e.target.value)}
            disabled={uploadMutation.isPending}
          />
          <Input
            ref={fileInputRef}
            type="file"
            accept=".md"
            onChange={handleFileChange}
            disabled={uploadMutation.isPending}
            required
            className="cursor-pointer file:cursor-pointer"
          />
          <Button
            type="submit"
            disabled={uploadMutation.isPending || !file}
            className="w-full"
          >
            {uploadMutation.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Analyzing Document...
              </>
            ) : (
              <>
                <Upload className="mr-2 h-4 w-4" />
                Upload & Verify
              </>
            )}
          </Button>
        </form>

        {/* Documents List */}
        <div className="flex-1 overflow-y-auto space-y-2 max-h-[400px] md:max-h-none">
          {isDocsLoading ? (
            <div className="flex items-center justify-center p-4">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : !docsData || docsData.count === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">
              No documents found.
            </p>
          ) : (
            docsData.data.map((doc) => (
              <button
                type="button"
                key={doc.id}
                onClick={() => {
                  setSelectedDoc(doc)
                  setChatMessages([])
                }}
                className={`p-3 rounded-lg border cursor-pointer hover:bg-accent transition-colors flex items-center justify-between gap-2 w-full text-left ${
                  selectedDoc?.id === doc.id
                    ? "bg-accent border-primary"
                    : "bg-background"
                }`}
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold truncate">{doc.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {new Date(doc.created_at).toLocaleDateString()}
                  </p>
                </div>
                {doc.is_accurate ? (
                  <CheckCircle2
                    className="h-4 w-4 text-green-500 shrink-0"
                  />
                ) : (
                  <AlertCircle
                    className="h-4 w-4 text-red-500 shrink-0"
                  />
                )}

              </button>
            ))
          )}
        </div>
      </div>

      {/* RIGHT COLUMN: Document View, Report & Chat */}
      <div className="flex-1 border rounded-lg p-6 bg-card flex flex-col gap-6">
        {!selectedDoc ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8 gap-3">
            <FileText className="h-16 w-16 text-muted-foreground opacity-50" />
            <h3 className="text-xl font-bold">No Document Selected</h3>
            <p className="text-muted-foreground max-w-sm">
              Select an existing document from the left list or upload a new
              markdown document to start reviewing accuracy reports and
              chatting.
            </p>
          </div>
        ) : (
          <div className="flex-1 flex flex-col gap-6">
            {/* Header info */}
            <div className="flex items-start justify-between border-b pb-4 gap-4">
              <div>
                <h1 className="text-2xl font-bold">{selectedDoc.title}</h1>
                <p className="text-sm text-muted-foreground">
                  Uploaded on{" "}
                  {new Date(selectedDoc.created_at).toLocaleString()}
                </p>
              </div>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => deleteMutation.mutate(selectedDoc.id)}
                disabled={deleteMutation.isPending}
              >
                <Trash2 className="h-4 w-4 mr-1" />
                Delete
              </Button>
            </div>

            {/* Accuracy Review Report */}
            <div className="border rounded-lg p-4 bg-muted/30">
              <h3 className="font-semibold text-lg mb-2 flex items-center gap-2">
                {selectedDoc.is_accurate ? (
                  <>
                    <CheckCircle2 className="h-5 w-5 text-green-500" />
                    Accuracy Verified (Gemma Agent)
                  </>
                ) : (
                  <>
                    <AlertCircle className="h-5 w-5 text-red-500" />
                    Review Recommended (Gemma Agent)
                  </>
                )}
              </h3>
              <div className="text-sm text-muted-foreground whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto border p-3 rounded bg-background">
                {selectedDoc.accuracy_report || "No review report available."}
              </div>
            </div>

            {/* Chatbot Interface */}
            <div className="flex-1 flex flex-col border rounded-lg bg-background overflow-hidden min-h-[350px]">
              <div className="border-b px-4 py-3 bg-muted/40 flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-primary" />
                <span className="font-semibold text-sm">
                  Ask Gemma about this Document (Greek Only)
                </span>
              </div>

              {/* Chat Messages */}
              <div className="flex-1 p-4 overflow-y-auto space-y-4 max-h-[300px]">
                {chatMessages.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-8">
                    Ask a question in Greek about the contents of this document.
                  </p>
                ) : (
                  chatMessages.map((msg, idx) => (
                    <div
                      key={idx}
                      className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                    >
                      <div
                        className={`max-w-[80%] rounded-lg px-4 py-2 text-sm leading-relaxed ${
                          msg.role === "user"
                            ? "bg-primary text-primary-foreground"
                            : "bg-muted text-muted-foreground"
                        }`}
                      >
                        {msg.text}
                      </div>
                    </div>
                  ))
                )}
                {isChatLoading && (
                  <div className="flex justify-start">
                    <div className="bg-muted text-muted-foreground rounded-lg px-4 py-2 text-sm flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Gemma is generating Greek response...
                    </div>
                  </div>
                )}
              </div>

              {/* Chat Input */}
              <form
                onSubmit={handleSendChat}
                className="border-t p-3 flex gap-2 bg-muted/10"
              >
                <Input
                  type="text"
                  placeholder="Ρωτήστε σχετικά με το έγγραφο (π.χ. Ποιο είναι το θέμα;)"
                  value={chatQuery}
                  onChange={(e) => setChatQuery(e.target.value)}
                  disabled={isChatLoading}
                  required
                />
                <Button
                  type="submit"
                  size="icon"
                  disabled={isChatLoading || !chatQuery.trim()}
                >
                  <Send className="h-4 w-4" />
                </Button>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
