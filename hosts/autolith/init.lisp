;;; Native Autolith adapter. Generated workflows remain derived from Claude files.
;;; Verified API baseline: Autolith 0.67.11. Site Lisp is trusted configuration,
;;; not an operating-system sandbox; ordinary native authorization still applies.
(in-package #:autolith)

(defparameter *workflow-site-root*
  (uiop:pathname-directory-pathname (or *load-truename* *user-init-pathname*)))
(defparameter *workflow-plugin-root*
  (truename (merge-pathnames "../../" *workflow-site-root*)))
(defparameter *workflow-initial-configuration* *user-init-configuration*)
(defparameter *workflow-catalog*
  (json-decode (uiop:read-file-string
                (merge-pathnames "hosts/catalog.json" *workflow-plugin-root*))))
(defparameter *workflow-role-policy*
  (json-decode (uiop:read-file-string
                (merge-pathnames "generated/policy.json" *workflow-site-root*))))
(defvar *workflow-correction-active-p* nil)
(defvar *workflow-result-decisions* nil)
(defvar *workflow-rendered-skills* nil)
(defvar *workflow-primary-role* nil)
(defvar *workflow-primary-conversation* nil)
(defvar *workflow-started-sessions* (make-hash-table :test #'equal))
(defvar *workflow-session-context* (make-hash-table :test #'equal))
(defvar *workflow-verified-completions* (make-hash-table :test #'eq))
(defvar *workflow-ui-applications* (make-hash-table :test #'eq))
(defvar *workflow-input-notice-active-p* nil)

(defun workflow-worker-turn-limit ()
  (let ((value (uiop:getenv "WORKFLOW_HOST_MAX_TURNS")))
    (when (and (equal (uiop:getenv "WORKFLOW_HOST_WORKER") "1")
               value (plusp (length value)))
      (let ((limit (parse-integer value :junk-allowed nil)))
        (unless (plusp limit)
          (error "WORKFLOW_HOST_MAX_TURNS must be positive."))
        limit))))

(defun workflow-working-directory (&optional configuration)
  (namestring
   (config :working-directory
           (or configuration *configuration* *user-init-configuration*
               *workflow-initial-configuration*))))

(defun workflow-bridge (arguments &key (input "") directory)
  "Call the shared Python behavior; process exits and JSON are both mandatory."
  (let ((directory (or directory (workflow-working-directory))))
    (multiple-value-bind (output diagnostics status)
        (uiop:run-program
         (append
          (list (or (uiop:getenv "WORKFLOW_PYTHON") "python3")
                (namestring (merge-pathnames "scripts/host-bridge.py"
                                            *workflow-plugin-root*)))
          arguments)
         :input (make-string-input-stream input)
         :output :string :error-output :string :ignore-error-status t
         :directory directory)
      (unless (eql status 0)
        (error "Workflow bridge failed (~A): ~A" status diagnostics))
      (let ((decoded (json-decode output)))
        (unless (json-object-p decoded)
          (error "Workflow bridge returned no JSON object."))
        decoded))))

(defun workflow-entry (kind name)
  (json-get (json-get *workflow-catalog*
                      (cond ((equal kind "command") "commands")
                            ((equal kind "skill") "skills")
                            ((equal kind "agent") "agents")
                            (t (error "Unknown workflow kind: ~A" kind))))
            name))

(defun workflow-render (kind name arguments directory)
  (json-get
   (workflow-bridge
    (list "render" "--host" "autolith" "--kind" kind "--name" name
          (concatenate 'string "--arguments=" arguments) "--project" directory)
    :directory directory)
   "prompt"))

(defun workflow-event (event configuration session &key tool-name tool-input
                        message error correction-p optional-p notification-type)
  "Adapt a native event to the existing hook JSON, never treating exit 0 as pass."
  (handler-case
      (workflow-bridge
       (list "event" "--event" event)
       :directory (workflow-working-directory configuration)
       :input
       (json-encode
        (json-object "hook_event_name" event
                     "cwd" (workflow-working-directory configuration)
                     "session_id" session
                     "tool_name" (or tool-name "")
                     "tool_input" (or tool-input (json-object))
                     "message" (or message "")
                     "notification_type" (or notification-type "")
                     "last_assistant_message" (or message "")
                     "error" (or error "")
                     "stop_hook_active" (if correction-p t (json-false)))))
    (error (condition)
      (if optional-p
          (json-object "action" "allow" "reason" (princ-to-string condition))
          (json-object "action" "halt"
                       "reason" (format nil "Workflow verification unavailable: ~A"
                                        condition))))))

(defun workflow-session (context)
  (conversation-identifier (tool-context-conversation context)))

(defun workflow-slash-arguments (remainder)
  "Preserve the complete command remainder as Claude's single argument string."
  (list remainder))

(defun workflow-attach-context (result event)
  "Retain native result metadata while adding advisory hook feedback."
  (let ((context (coerce (json-get event "context") 'list)))
    (when context
      (let ((message (format nil "~{~A~^~%~}" context))
            (original (tool-result-content result))
            (blocks (tool-result-content-blocks result)))
        (setf (slot-value result 'content)
              (bounded-string (format nil "~A~%~A" original message)
                              :limit 8000)
              (slot-value result 'content-blocks)
              (tool-result--normalize-content-blocks
               (append (or blocks (list original)) (list message)))))))
  result)

(defun workflow-invoke (application kind name arguments)
  "Only an explicit registered user operation injects a user-only workflow."
  (let ((entry (workflow-entry kind name)))
    (unless (and entry (json-true-p (json-get entry "user_invocable")))
      (error "Workflow ~A is not user-invocable." name))
    (application-submit-prompt
     application "autolith"
     (workflow-render kind name arguments
                      (workflow-working-directory
                       (application-configuration application))))))

(defun workflow-generated-skill-p (metadata)
  (uiop:subpathp (skill-metadata-pathname metadata)
                (merge-pathnames "skills/" *workflow-site-root*)))

;; Keep cl-skills' parser and source validation intact. Only the final Autolith
;; contribution from this site's resources is rendered, once per logical turn.
(defvar *workflow-original-skill-instruction*
  (symbol-function 'skill--explicit-instruction))
(setf (symbol-function 'skill--explicit-instruction)
      (lambda (metadata instructions)
        (funcall
         *workflow-original-skill-instruction* metadata
         (if (workflow-generated-skill-p metadata)
             (let* ((name (skill-metadata-name metadata))
                    (kind (if (workflow-entry "skill" name) "skill" "command"))
                    (key (list kind name (workflow-working-directory))))
               (or (and *workflow-rendered-skills*
                        (gethash key *workflow-rendered-skills*))
                   (let ((rendered (workflow-render kind name ""
                                                    (workflow-working-directory))))
                     (when *workflow-rendered-skills*
                       (setf (gethash key *workflow-rendered-skills*) rendered))
                     rendered)))
             instructions))))

(defmethod task-agent-definition-instructions :around
    ((definition task-agent-definition))
  "Render only roles supplied by this site, retaining user/project overrides."
  (let ((pathname (task-agent-definition-pathname definition)))
    (if (or (and (equal (uiop:getenv "WORKFLOW_HOST_WORKER") "1")
                 (equal (task-agent-definition-name definition)
                        (uiop:getenv "WORKFLOW_HOST_ROLE")))
            (and pathname
                 (uiop:subpathp pathname (merge-pathnames "agents/" *workflow-site-root*))))
        (workflow-render "agent" (task-agent-definition-name definition) ""
                         (workflow-working-directory))
        (call-next-method))))

(defmethod task-agent-definition-spawns :around
    ((definition task-agent-definition))
  (if (equal (uiop:getenv "WORKFLOW_HOST_WORKER") "1")
      nil
      (call-next-method)))

(defmethod task-agent-definition-tools :around
    ((definition task-agent-definition))
  (let ((policy (json-get *workflow-role-policy*
                          (task-agent-definition-name definition))))
    (if (and policy (equal (uiop:getenv "WORKFLOW_HOST_WORKER") "1"))
        (coerce (json-get policy "tools") 'list)
        (call-next-method))))

(defun workflow-role-tool-p (name tool)
  (let* ((entry (json-get *workflow-role-policy* name))
         (tools (and entry (json-get entry "tools"))))
    (and tools
         (or (some (lambda (spec) (task--tool-spec-matches-p spec tool))
                   (coerce tools 'list))
             (and (plusp (length (json-get entry "spawns")))
                  (member (tool-canonical-name tool) '("task.run" "task.agents")
                          :test #'equal))))))

(defun workflow-evaluator-p (context)
  (or (equal (uiop:getenv "WORKFLOW_HOST_ROLE") "evaluator")
      (and (equal *workflow-primary-role* "evaluator")
           (equal (workflow-session context) *workflow-primary-conversation*))
      (let ((agent (tool-context-agent context)))
        (and (typep agent 'task-child-agent)
             (equal (task-agent-definition-name
                     (task-child-agent-definition agent)) "evaluator")))))

(defun workflow-resource-path (arguments)
  "Normalize workspace resource identities before passing them to hook policy."
  (let ((uri (or (json-get arguments "uri") "")))
    (if (uiop:string-prefix-p "workspace:" uri)
        (quri:url-decode (subseq uri (length "workspace:")))
        (quri:url-decode uri))))

(defun workflow-protected-evaluator-path-p (path)
  (some (lambda (part)
          (or (member part '(".aws" ".ssh" "secrets") :test #'equal)
              (equal part ".env")
              (uiop:string-prefix-p ".env." part)))
        (uiop:split-string path :separator '(#\/ #\\))))

(defun workflow-bundled-source (context path)
  "Identify a catalog-owned file after native canonical/symlink resolution."
  (when path
    (let ((canonical (workspace-tool-resolve-path context path)))
      (when (uiop:subpathp canonical *workflow-plugin-root*)
        (let ((source (enough-namestring canonical *workflow-plugin-root*)))
          (when (json-get (json-get *workflow-catalog* "sources") source)
            (values source canonical)))))))

(defun workflow-render-read-result (result context source)
  "Adapt displayed instruction text while retaining native observations/anchors."
  (let ((cache (make-hash-table :test #'equal)))
    (labels ((render (text)
               (or (gethash text cache)
                   (setf
                    (gethash text cache)
                    (json-get
                     (workflow-bridge
                      (list "render-text" "--host" "autolith" "--source" source
                            "--project" (workflow-working-directory
                                         (tool-context-configuration context)))
                      :input text
                      :directory (workflow-working-directory
                                  (tool-context-configuration context)))
                     "text")))))
      (setf (slot-value result 'content)
            (bounded-string (render (tool-result-content result)) :limit 8000)
            (slot-value result 'content-blocks)
            (tool-result--normalize-content-blocks
             (mapcar (lambda (block) (if (stringp block) (render block) block))
                     (tool-result-content-blocks result)))))
    result))

;; Give this adapter a distinct method specializer. Replacing the native
;; (TOOL TOOL-CONTEXT HASH-TABLE) :around method would erase context rules.
(defclass workflow-tool-context (tool-context) ())
(defmethod initialize-instance :around
    ((context tool-context) &rest arguments &key &allow-other-keys)
  (declare (ignore arguments))
  (prog1 (call-next-method)
    (unless (typep context 'workflow-tool-context)
      (change-class context 'workflow-tool-context))))

(defmethod tool-execute :around
    ((tool tool) (context workflow-tool-context) (arguments hash-table))
  "Apply shared pre-tool checks to shell AND resource operations."
  (let* ((name (tool-canonical-name tool))
         (configuration (tool-context-configuration context))
         (session (workflow-session context))
         (claude-name
           (cond ((equal name "shell.run") "Bash")
                 ((equal name "resource.read") "Read")
                 ((equal name "resource.edit") "Edit")))
         (path (and (member name '("resource.read" "resource.edit") :test #'equal)
                    (workflow-resource-path arguments)))
         (input (if (equal name "shell.run")
                    (json-object "command" (json-get arguments "command"))
                    (json-object "file_path" (or path "")))))
    (when (and (equal (uiop:getenv "WORKFLOW_HOST_WORKER") "1")
               (or (uiop:string-prefix-p "task." name)
                   (uiop:string-prefix-p "job." name)
                   (and (not (equal name "yield.submit"))
                        (not (workflow-role-tool-p
                              (uiop:getenv "WORKFLOW_HOST_ROLE") tool)))))
      (return-from tool-execute
        (tool-failure "The controller's worker tool policy denies this operation."
                      :denied-p t)))
    (when (and *workflow-primary-role*
               (equal session *workflow-primary-conversation*)
               (not (workflow-role-tool-p *workflow-primary-role* tool)))
      (return-from tool-execute
        (tool-failure (format nil "Role ~A cannot use ~A."
                              *workflow-primary-role* name) :denied-p t)))
    (when (and (equal name "task.run") *workflow-primary-role*
               (equal session *workflow-primary-conversation*))
      (let* ((policy (json-get *workflow-role-policy* *workflow-primary-role*))
             (allowed (coerce (json-get policy "spawns") 'list))
             (tasks (if (json-get arguments "tasks")
                        (coerce (json-get arguments "tasks") 'list)
                        (list arguments))))
        (unless (every (lambda (task)
                         (member (or (json-get task "agent") "task") allowed
                                 :test #'equal)) tasks)
          (return-from tool-execute
            (tool-failure "The selected role cannot spawn that child role."
                          :denied-p t)))))
    (when (and path (workflow-evaluator-p context)
               (workflow-protected-evaluator-path-p path))
      (return-from tool-execute
        (tool-failure "Evaluator access to a protected resource is denied."
                      :denied-p t)))
    (when claude-name
      (let ((decision (workflow-event "PreToolUse" configuration session
                                     :tool-name claude-name :tool-input input)))
        (unless (equal (json-get decision "action") "allow")
          (return-from tool-execute
            (tool-failure (json-get decision "reason") :denied-p t)))))
    (when (equal name "skill.load")
      (let* ((skill-name (json-get arguments "name"))
             (entry (or (workflow-entry "skill" skill-name)
                        (workflow-entry "command" skill-name))))
        (when (and entry
                   (or (not (json-true-p (json-get entry "model_invocable")))
                       (and *application-local-user-evaluation-p*
                            (not (json-true-p (json-get entry "user_invocable"))))))
          (return-from tool-execute
            (tool-failure "This workflow cannot be invoked through skill.load."
                          :denied-p t)))))
    (let* ((bundle-path (and (equal name "resource.read")
                             (nth-value 1 (workflow-bundled-source context path))))
           ;; The native root protocol accepts directories. Bind the containing
           ;; directory only after this read's exact canonical file matched the
           ;; catalog. The binding ends with this single read; edits and other
           ;; paths never receive it, and native canonicalization rejects links
           ;; escaping the configured package root.
           (*workspace-tool-readable-roots*
             (if bundle-path
                 (cons (uiop:pathname-directory-pathname bundle-path)
                       (workspace-tool-readable-roots context))
                 *workspace-tool-readable-roots*))
           (result (call-next-method)))
      (when (and (equal name "resource.read") (tool-result-success-p result))
        (let ((source (workflow-bundled-source context path)))
          (when (and source (uiop:string-suffix-p source ".md"))
            (handler-case
                (workflow-render-read-result result context source)
              (error (condition)
                (return-from tool-execute
                  (tool-failure
                   (format nil "Workflow instructions could not be rendered: ~A" condition))))))))
      (cond
        ((not (tool-result-success-p result))
         (workflow-attach-context
          result
          (workflow-event "PostToolUseFailure" configuration session
                          :tool-name (or claude-name name) :tool-input input
                          :error (tool-result-content result) :optional-p t)))
        ((equal name "resource.edit")
         (workflow-attach-context
          result (workflow-event "PostToolUse" configuration session
                                 :tool-name "Edit" :tool-input input :optional-p t))))
      result)))

;; Preserve Autolith's telemetry :around method on USER-MESSAGE-INPUT as well.
(defclass workflow-user-message-input (user-message-input) ())
(defmethod initialize-instance :around
    ((content user-message-input) &rest arguments &key &allow-other-keys)
  (declare (ignore arguments))
  (prog1 (call-next-method)
    (unless (typep content 'workflow-user-message-input)
      (change-class content 'workflow-user-message-input))))

(defmethod agent-run-user-turn :around
    ((agent agent) (content workflow-user-message-input) &rest options &key &allow-other-keys)
  "Scope correction continuity to a real user turn, leaving retries to Python."
  (let* ((*workflow-correction-active-p* nil)
         (*workflow-result-decisions* (make-hash-table :test #'eq))
         (*workflow-rendered-skills* (make-hash-table :test #'equal))
         (role (if (typep agent 'task-child-agent)
                   (task-agent-definition-name (task-child-agent-definition agent))
                   *workflow-primary-role*))
         (role-limit (and role
                          (json-get (json-get *workflow-role-policy* role)
                                    "max_turns")))
         (*agent-maximum-provider-requests-per-turn*
           (min (or (workflow-worker-turn-limit)
                    *agent-maximum-provider-requests-per-turn*)
                (if (and (integerp role-limit) (plusp role-limit))
                    role-limit *agent-maximum-provider-requests-per-turn*)
                *agent-maximum-provider-requests-per-turn*))
         (*agent-restricted-maximum-tool-rounds*
           (if (and (integerp role-limit) (plusp role-limit))
               role-limit *agent-restricted-maximum-tool-rounds*))
         (configuration (agent-configuration agent))
         (session (conversation-identifier (agent-conversation agent))))
    ;; A previous provider result cannot certify new user or continuation work.
    (remhash agent *workflow-verified-completions*)
    (unless (gethash session *workflow-started-sessions*)
      (setf (gethash session *workflow-started-sessions*) t)
      (let ((event (workflow-event "SessionStart" configuration session :optional-p t)))
        (setf (gethash session *workflow-session-context*)
              (coerce (json-get event "context") 'list))))
    (handler-case
        (if (and *workflow-primary-role*
                 (equal session *workflow-primary-conversation*))
            (let ((options (copy-list options)))
              (setf (getf options :tool-allowlist)
                    (loop for tool in (tool-registry-tools (agent-tool-registry agent))
                          when (workflow-role-tool-p *workflow-primary-role* tool)
                            collect (tool-canonical-name tool))
                    (getf options :tool-restriction-p) t)
              (apply #'call-next-method agent content options))
            (call-next-method))
      (provider-error (condition)
        (workflow-event "StopFailure" configuration session
                        :error (princ-to-string condition) :optional-p t)
        (error condition)))))

(defmethod agent-turn-complete-p :around
    ((agent agent) (result provider-result))
  "A native provider-loop boundary, including ordinary turns outside missions."
  (let ((complete (call-next-method)))
    (if (or (not complete)
            (typep agent 'task-child-agent)
            (equal (uiop:getenv "WORKFLOW_HOST_WORKER") "1"))
        complete
        (let* ((decision
                 (or (and *workflow-result-decisions*
                          (gethash result *workflow-result-decisions*))
                     (workflow-event
                      "Stop" (agent-configuration agent)
                      (conversation-identifier (agent-conversation agent))
                      :message (or (provider-result-assistant-text result) "")
                      :correction-p *workflow-correction-active-p*)))
               (action (json-get decision "action")))
          (when *workflow-result-decisions*
            (setf (gethash result *workflow-result-decisions*) decision))
          (cond
            ((equal action "allow")
             ;; This is evidence for a later application boundary, never a
             ;; desktop notification: native jobs/goals may still continue.
             (setf (gethash agent *workflow-verified-completions*) result)
             t)
            ((equal action "repair")
             (remhash agent *workflow-verified-completions*)
             (setf *workflow-correction-active-p* t)
             (unless (json-get decision "autolith_feedback_sent")
               (setf (gethash "autolith_feedback_sent" decision) t)
               (conversation-append-user-message
                (agent-conversation agent)
                (format nil "Required workflow verification failed. ~A"
                        (json-get decision "reason"))
                :automatic-p t))
             nil)
            (t
             (remhash agent *workflow-verified-completions*)
             (error 'agent-loop-error
                    :conversation-id (conversation-identifier
                                      (agent-conversation agent))
                    :request-number nil
                    :message (format nil "Workflow completion blocked: ~A"
                                     (json-get decision "reason")))))))))

;;; Desktop notices belong to native application/input boundaries. In
;;; particular, agent-turn-complete-p is too early: the application can still
;;; run goal continuations or resume a detached job's completion afterwards.
(defmethod initialize-instance :around
    ((controller application-input-controller) &rest arguments &key &allow-other-keys)
  (declare (ignore arguments))
  (prog1 (call-next-method)
    (let* ((application (application-input-controller-application controller))
           (ui (and (slot-boundp application 'ui) (application-ui application))))
      (when ui (setf (gethash ui *workflow-ui-applications*) application)))))

(defun workflow-peer-input-p (agent)
  "Inspect native mailbox ownership without claiming or acknowledging input."
  (let ((service (peer-message-service-find agent)))
    (when service
      (with-recursive-lock-held ((peer-message-lock service))
        (let ((receiver (peer-message--endpoint-id (peer-message--actor-endpoint agent))))
          (some (lambda (message)
                  (and (equal receiver (getf message :receiver))
                       (member (getf message :state) '(:queued :delivered :unknown))))
                (getf (cl-jobpond:mailbox-snapshot (peer-message-mailbox service)) :messages)))))))

(defun workflow-application-settled-p (controller)
  "Require verified completion and no native foreground or durable work."
  (let* ((application (application-input-controller-application controller))
         (agent (application-agent application))
         (goal (application-goal application))
         (ui (application-ui application)))
    (and (not (equal (uiop:getenv "WORKFLOW_HOST_WORKER") "1"))
         (gethash agent *workflow-verified-completions*)
         (not (application-input-controller-busy-p controller))
         (not (application-input-controller-stopping-p controller))
         (not (application-input-controller-failure controller))
         (not (application-input-controller-queued-work-paused-p controller))
         (not (application-input-controller-turn-cancellation-p controller))
         (not (application-input-controller-localgroup-handoff-p controller))
         (not (application-localgroup-paused-p application))
         (not (application-localgroup-handoff-pending-p application))
         (not (and ui (eq (first (terminal-ui-program-status ui)) :blocked)))
         ;; Completed goals and verified missions are the only goal states
         ;; proving completion. Paused/blocked/exhausted/cancelled are unfinished.
         (or (null goal)
             (eq (getf goal :status) (if (mission-goal-p goal) :verified :complete)))
         (zerop (getf (task-unfinished-work-snapshot agent :limit 0) :total))
         (null (task-completion-pending agent))
         (not (workflow-peer-input-p agent)))))

(defun workflow-notify-settled (controller)
  "Consume one verified completion only after native application work settles."
  (handler-case
      (when (workflow-application-settled-p controller)
        (let* ((application (application-input-controller-application controller))
               (agent (application-agent application)))
          (remhash agent *workflow-verified-completions*)
          (workflow-event "Notification" (application-configuration application)
                          (conversation-identifier (application-conversation application))
                          :notification-type "idle_prompt"
                          :message "Autolith finished all work and required verification."
                          :optional-p t)))
    ;; Notification availability must never change native work/authorization.
    (error () nil)))

(defvar *workflow-original-finish-work*
  (symbol-function 'application-input-controller--finish-work))
(defvar *workflow-original-begin-work*
  (symbol-function 'application-input-controller--begin-prompt-work))
(setf (symbol-function 'application-input-controller--begin-prompt-work)
      (lambda (controller work)
        ;; A queued command/Lisp operation can change source without a model
        ;; turn. It must not reuse an earlier turn's passing verification.
        (unless (member (first work) '(:job-completion-maintenance :idle-compaction))
          (remhash (application-agent (application-input-controller-application controller))
                   *workflow-verified-completions*))
        (funcall *workflow-original-begin-work* controller work)))
(setf (symbol-function 'application-input-controller--finish-work)
      (lambda (controller)
        ;; Native cleanup clears cancellation/status, so retain them first.
        (let ((failed-p (or (application-input-controller-turn-cancellation-p controller)
                            (application-input-controller-turn-cancellation-delivery-pending-p controller)
                            (not (zerop (application-input-controller-prompt-marker-status controller))))))
          (prog1 (funcall *workflow-original-finish-work* controller)
            (if failed-p
                (remhash (application-agent (application-input-controller-application controller))
                         *workflow-verified-completions*)
                (workflow-notify-settled controller))))))

(defvar *workflow-original-blocked-input*
  (symbol-function 'terminal-ui-call-with-blocked-status))
(setf (symbol-function 'terminal-ui-call-with-blocked-status)
      (lambda (ui kind function)
        (funcall *workflow-original-blocked-input* ui kind
                 (lambda ()
                   ;; The native caller has acquired exclusive input and set
                   ;; :blocked. Saved/automatic authorizations never reach here.
                   (let* ((application (gethash ui *workflow-ui-applications*))
                          (controller (and application (application-input-controller application))))
                     (when (and controller
                                (application-input-controller-turn-active-p controller)
                                (member kind '(:permission :question))
                                (not *workflow-input-notice-active-p*)
                                (not (equal (uiop:getenv "WORKFLOW_HOST_WORKER") "1")))
                       (workflow-event "Notification" (application-configuration application)
                                       (conversation-identifier (application-conversation application))
                                       :notification-type (if (eq kind :permission)
                                                              "permission_prompt" "elicitation_dialog")
                                       :message (if (eq kind :permission)
                                                    "Autolith is waiting for your permission."
                                                    "Autolith is waiting for your answer.")
                                       :optional-p t))
                     (let ((*workflow-input-notice-active-p* t))
                       (funcall function)))))))

(define-context-contributor workflow-host-context (request)
  (let* ((configuration (request-context-configuration request))
         (conversation (request-context-conversation request))
         (role (and (equal (conversation-identifier conversation)
                           *workflow-primary-conversation*)
                    *workflow-primary-role*)))
    (list
     (make-context-contribution
      :identifier "agentic-coding-workflow-host"
      :instruction
      (format nil "Workflow host: Autolith. Plugin root: ~A. Project root: ~A.~%~{~A~%~}~A"
              (namestring *workflow-plugin-root*)
              (workflow-working-directory configuration)
              (gethash (conversation-identifier conversation) *workflow-session-context*)
              (if role
                  (workflow-render "agent" role ""
                                   (workflow-working-directory configuration))
                  "Use native Autolith tools; plugin workflows use /workflow-NAME."))
      :priority 950 :class ':mandatory
      :deduplication-key "agentic-coding-workflow-host"))))

;; Autolith has no positional CLI prompt. Its own startup controller queue is
;; the supported point for submitting a role task or native goal from a launcher.
(defvar *workflow-original-application-run* (symbol-function 'application-run))
(defun workflow-restored-role (conversation)
  "Restore the role from native durable metadata, including rotated segments."
  (let ((selected nil))
    (when (conversation-persisted-p conversation)
      (conversation-map-records
       conversation
       (lambda (record)
         (when (eq (first record) :provider)
           (let* ((metadata (getf (rest record) :metadata))
                  (role (getf metadata :workflow-host-role)))
             (when (and (eql (getf metadata :workflow-host-schema) 1)
                        (stringp role))
               (unless (workflow-entry "agent" role)
                 (error "Saved workflow role is unavailable: ~A" role))
               (setf selected role)))))))
    selected))

(setf (symbol-function 'application-run)
      (lambda (application &rest options)
        (let* ((explicit-role (uiop:getenv "WORKFLOW_HOST_ROLE"))
               (conversation (application-conversation application))
               (role (if (and explicit-role (plusp (length explicit-role)))
                         explicit-role
                         (workflow-restored-role conversation)))
               (initial (uiop:getenv "WORKFLOW_HOST_INITIAL_PROMPT"))
               (goal (uiop:getenv "WORKFLOW_HOST_GOAL")))
          (when (and (not (equal (uiop:getenv "WORKFLOW_HOST_WORKER") "1"))
                     role (plusp (length role)))
            (unless (workflow-entry "agent" role)
              (error "Unknown workflow role: ~A" role))
            (setf *workflow-primary-role* role
                  *workflow-primary-conversation*
                  (conversation-identifier conversation))
            (when (and explicit-role (plusp (length explicit-role)))
              (conversation-append-provider-metadata
               conversation (list :workflow-host-schema 1 :workflow-host-role role))))
          (when (and (not (equal (uiop:getenv "WORKFLOW_HOST_WORKER") "1"))
                     (or (and initial (plusp (length initial)))
                         (and goal (plusp (length goal)))))
            (when (getf options :initial-command)
              (error "Cannot combine native startup command and workflow initial task."))
            (setf (getf options :initial-command)
                  (if (and goal (plusp (length goal)))
                      (format nil "(goal ~S)" goal)
                      (format nil "(prompt ~S)" initial))))
          (apply *workflow-original-application-run* application options))))

(platform-setenv "CLAUDE_PLUGIN_ROOT" (namestring *workflow-plugin-root*))
(platform-setenv "WORKFLOW_HOST" "autolith")
(load (merge-pathnames "generated/commands.lisp" *workflow-site-root*))
