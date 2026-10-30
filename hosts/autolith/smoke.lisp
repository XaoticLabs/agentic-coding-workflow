;;; Real Autolith smoke exercise. Loaded only by tests/smoke_autolith.py.
;;; It invokes native parsers and tool/completion dispatch without inference.
(in-package #:autolith)

(defclass workflow-smoke-application (application)
  ((submitted :initform nil :accessor workflow-smoke-submitted)))

(defmethod application-submit-prompt
    ((application workflow-smoke-application) target input &key prefer-steering-p)
  (declare (ignore target prefer-steering-p))
  (setf (workflow-smoke-submitted application) input))

(defun workflow-smoke-result (identifier)
  (make-instance 'provider-result :response-id identifier :output-items nil
                 :tool-calls nil :usage (json-object) :turn-completion ':end))

;; Exercise the real native modal picker without a terminal or desktop side effect.
(defclass workflow-smoke-terminal (terminal)
  ((events :initform nil :accessor workflow-smoke-terminal-events)
   (on-read :initform nil :accessor workflow-smoke-terminal-on-read)))
(defmethod terminal--write ((terminal workflow-smoke-terminal) (text string))
  (declare (ignore terminal text)) nil)
(defmethod terminal-flush ((terminal workflow-smoke-terminal))
  (declare (ignore terminal)) nil)
(defmethod terminal-start ((terminal workflow-smoke-terminal))
  (setf (terminal-started-p terminal) t (terminal-interactive-p terminal) t) terminal)
(defmethod terminal-stop ((terminal workflow-smoke-terminal))
  (setf (terminal-started-p terminal) nil (terminal-interactive-p terminal) nil) terminal)
(defmethod terminal-input-ready-p ((terminal workflow-smoke-terminal))
  (not (null (workflow-smoke-terminal-events terminal))))
(defmethod terminal-read-event ((terminal workflow-smoke-terminal))
  (when (workflow-smoke-terminal-on-read terminal)
    (funcall (workflow-smoke-terminal-on-read terminal)))
  (or (pop (workflow-smoke-terminal-events terminal)) :end-of-input))

(defun workflow-smoke-notifications (passed configuration conversation registry agent project)
  (let* ((terminal (make-instance 'workflow-smoke-terminal :columns 80))
         (ui (terminal-ui-create :terminal terminal))
         (application (make-instance 'application :configuration configuration
                                     :conversation conversation :tool-registry registry
                                     :agent agent :provider nil :worker nil :ui ui))
         (runtime (or (task-completion--runtime agent)
                      (let ((runtime (task-orchestrator-create)))
                        (tool-registry-bind-runtime registry 'task-orchestrator runtime)
                        runtime)))
         (controller (application-input-controller-create application
                      :load-pending-p nil :pending-persistence-enabled-p nil :start-reader-p nil))
         (*workflow-verified-completions* (make-hash-table :test #'eq))
         (*workflow-result-decisions* (make-hash-table :test #'eq))
         (*workflow-correction-active-p* nil)
         (original-event (symbol-function 'workflow-event))
         (notices nil))
    (unwind-protect
         (progn
           (setf (symbol-function 'workflow-event)
                 (lambda (event configuration session &rest options)
                   (if (equal event "Notification")
                       (progn (push (list :type (getf options :notification-type)
                                          :blocked (eq (first (terminal-ui-program-status ui)) :blocked))
                                    notices)
                              (json-object "action" "allow"))
                       (apply original-event event configuration session options))))
           (with-open-file (stream (merge-pathnames "accepted.flag" project)
                                   :direction :output :if-exists :supersede)
             (write-line "accepted" stream))
           (application-input-controller--finish-work controller)
           (funcall passed "unverified-application-never-notifies" (null notices))
           (funcall passed "verified-provider-result-never-notifies"
                    (and (agent-turn-complete-p agent (workflow-smoke-result "notify-verified"))
                         (null notices)))
           (setf (application-input-controller-active-p controller) t)
           (workflow-notify-settled controller)
           (funcall passed "active-application-never-notifies" (null notices))
           (setf (application-input-controller-active-p controller) nil)
           (dolist (queue (application-input-controller--queues controller))
             (deque-push-back queue '(:fixture))
             (workflow-notify-settled controller)
             (deque-pop-front queue))
           (funcall passed "all-native-pending-input-queues-suppress-finished" (null notices))
           (dolist (kind '(nil :mission))
             (dolist (status '(:active :paused :blocked :exhausted :cancelled))
               (setf (application-goal application) (list :kind kind :status status))
               (application-input-controller--finish-work controller)))
           (funcall passed "pending-goals-and-missions-never-notify" (null notices))
           (setf (application-goal application) nil)
           (let* ((entered (sb-thread:make-semaphore))
                  (release (sb-thread:make-semaphore))
                  (job (task-orchestrator-start-execution-job
                        runtime agent :tool-name "workflow.notification.fixture"
                        :summary "Pending work blocks completion notices"
                        :detached-p t :completion-policy :continue
                        :operation-function
                        (lambda ()
                          (sb-thread:signal-semaphore entered)
                          (sb-thread:wait-on-semaphore release)
                          (tool-success "Fixture work complete")))))
             (unwind-protect
                  (progn
                    (task-completion-watch job agent)
                    (funcall passed "native-notification-job-started"
                             (sb-thread:wait-on-semaphore entered :timeout 10))
                    (application-input-controller--finish-work controller)
                    (funcall passed "running-native-job-never-notifies" (null notices))
                    (sb-thread:signal-semaphore release)
                    (session-job-await job 10)
                    (cl-jobpond:completion-subscription-refresh
                     (task-completion-service-subscription (task-completion--service agent)))
                    (application-input-controller--finish-work controller)
                    (funcall passed "undelivered-native-job-never-notifies"
                             (and (task-completion-pending agent) (null notices)))
                    (task-completion-deliver agent)
                    (application-input-controller--finish-work controller)
                    (application-input-controller--finish-work controller)
                    (funcall passed "exactly-one-fully-finished-notification"
                             (and (= 1 (length notices))
                                  (equal "idle_prompt" (getf (first notices) :type)))))
               (sb-thread:signal-semaphore release)
               (session-job-await job 10)))
           (setf notices nil)
           (dolist (failure '(:cancelled :failed))
             (setf (gethash agent *workflow-verified-completions*) (workflow-smoke-result "stale")
                   (application-input-controller-turn-cancellation-p controller) (eq failure :cancelled)
                   (application-input-controller-prompt-marker-status controller) (if (eq failure :failed) 1 0))
             (application-input-controller--finish-work controller)
             (application-input-controller--finish-work controller))
           (funcall passed "cancelled-or-failed-work-never-notifies" (null notices))
           (setf (gethash agent *workflow-verified-completions*) (workflow-smoke-result "before-command"))
           (application-input-controller--begin-prompt-work controller '(:native-lisp "nil"))
           (application-input-controller--finish-work controller)
           (funcall passed "queued-command-invalidates-prior-verification" (null notices))
           (terminal-ui-start ui)
           (setf (application-input-controller-active-p controller) t
                 (workflow-smoke-terminal-events terminal) '(:down :submit)
                 (workflow-smoke-terminal-on-read terminal)
                 (lambda ()
                   (unless (and (= 1 (length notices))
                                (getf (first notices) :blocked)
                                (equal "permission_prompt" (getf (first notices) :type)))
                     (error "Permission notice did not precede actual modal input."))))
           (funcall passed "actual-native-permission-pause-notifies-once"
                    (and (eq (application-authorize-command application "workflow-smoke-once"
                                                            (pathname project)) :full-access)
                         (= 1 (length notices))))
           (setf (workflow-smoke-terminal-on-read terminal) nil
                 (application-permission-mode application) :full-access)
           (application-authorize-command application "workflow-smoke-automatic" (pathname project))
           (funcall passed "automatic-permission-never-notifies" (= 1 (length notices)))
           (setf notices nil (workflow-smoke-terminal-events terminal) '(:submit))
           (terminal-ui-select ui :items '((:name "fixture answer" :description "")))
           (funcall passed "actual-native-question-pause-notifies-once"
                    (and (= 1 (length notices))
                         (equal "elicitation_dialog" (getf (first notices) :type))
                         (getf (first notices) :blocked)))
           (setf notices nil)
           (terminal-ui-call-with-blocked-status
            ui :question
            (lambda () (terminal-ui-call-with-blocked-status ui :permission (lambda () :answered))))
           (funcall passed "nested-input-pause-notices-coalesced" (= 1 (length notices)))
           (funcall passed "native-input-status-restored"
                    (not (eq (first (terminal-ui-program-status ui)) :blocked))))
      (setf (symbol-function 'workflow-event) original-event)
      (terminal-ui-stop ui)
      (remhash ui *workflow-ui-applications*)
      (when (probe-file (merge-pathnames "accepted.flag" project))
        (delete-file (merge-pathnames "accepted.flag" project))))))

(defun workflow-smoke (project report)
  (let* ((configuration
           (configuration-copy *user-init-configuration*
                               :working-directory (uiop:ensure-directory-pathname project)
                               :site-config-root *workflow-site-root*))
         (*configuration* configuration)
         (conversation (conversation-create
                        configuration :identifier "workflow-smoke"
                        :storage-root (merge-pathnames ".claude/native-conversations/" project)))
         (registry (make-default-tool-registry :configuration configuration :immutable-p t))
         (agent (make-instance 'agent :configuration configuration
                               :conversation conversation :tool-registry registry
                               :worker nil))
         (authorized-p nil)
         (context (make-instance 'tool-context :configuration configuration
                                  :conversation conversation :registry registry
                                  :agent agent :worker nil
                                  :command-authorization-function
                                  (lambda (command directory)
                                    (declare (ignore command directory))
                                    (setf authorized-p t)
                                    ':deny)))
         (criteria (json-object)))
    (labels ((passed (name assertion)
               (unless assertion (error "Autolith smoke criterion failed: ~A" name))
               (setf (gethash name criteria) t)))
      (unwind-protect
           (progn
             (passed "native-context-rules-preserved"
                     (find-method #'tool-execute '(:around)
                                  (list (find-class 'tool) (find-class 'tool-context)
                                        (find-class 'hash-table))))
             (passed "native-context-initialization-preserved"
                     (find-method #'initialize-instance '(:after)
                                  (list (find-class 'tool-context))))
             (passed "native-telemetry-preserved"
                     (find-method #'agent-run-user-turn '(:around)
                                  (list (find-class 'agent) (find-class 'user-message-input))))
             (let ((result (workflow-attach-context
                            (tool-failure "Original fixture failure")
                            (json-object "context" #("Advisory fixture feedback")))))
               (passed "advisory-feedback-preserves-native-tool-output"
                       (and (member "Original fixture failure"
                                    (tool-result-content-blocks result) :test #'equal)
                            (member "Advisory fixture feedback"
                                    (tool-result-content-blocks result) :test #'equal))))
             (let* ((input "/workflow-implement --plan \"task with spaces\"")
                    (invocation (application-command-invocation-parse input))
                    (application (make-instance 'workflow-smoke-application
                                                :configuration configuration
                                                :conversation conversation
                                                :tool-registry registry :agent agent
                                                :provider nil :worker nil :ui nil)))
               (application-command-execute (application-command-find "/workflow-implement")
                                             application invocation)
               (passed "native-user-command-preserves-arguments"
                       (and (equal (application-command-invocation-arguments invocation)
                                   '("--plan \"task with spaces\""))
                            (search "--plan \"task with spaces\""
                                    (workflow-smoke-submitted application)))))
             (let ((catalog (skill-catalog-for-configuration configuration)))
               (passed "leading-command-flags-render"
                       (search "--workflow-smoke-leading-flag"
                               (workflow-render "command" "dashboard"
                                                "--workflow-smoke-leading-flag" project)))
               (maphash
                (lambda (name entry)
                  (passed (format nil "skill-policy-~A" name)
                          (and
                           (eq (not (null (skill-catalog-find catalog name)))
                               (json-true-p (json-get entry "model_invocable")))
                           (eq (not (null (application-command-find
                                          (format nil "/workflow-~A" name))))
                               (json-true-p (json-get entry "user_invocable"))))))
                (json-get *workflow-catalog* "skills"))
               (maphash
                (lambda (name entry)
                  (passed (format nil "command-policy-~A" name)
                          (and
                           (eq (not (null (skill-catalog-find catalog name)))
                               (json-true-p (json-get entry "model_invocable")))
                           (eq (not (null (application-command-find
                                          (format nil "/workflow-~A" name))))
                               (json-true-p (json-get entry "user_invocable"))))))
                (json-get *workflow-catalog* "commands"))
               (let* ((metadata (skill-catalog-find catalog "improve-workflow"))
                      (rendered (skill--explicit-instruction
                                 metadata (skill-metadata-read metadata))))
                 (passed "native-skill-runtime-rendering"
                         (and (search "Workflow host: autolith" rendered)
                              (search (namestring *workflow-plugin-root*) rendered)
                              (not (search "${CLAUDE_PROJECT_DIR}" rendered))))))
             (multiple-value-bind (definitions diagnostics) (task-discover-agents configuration)
               (passed "native-role-validation" (null diagnostics))
               (maphash
                (lambda (name entry)
                  (declare (ignore entry))
                  (passed (format nil "native-role-~A" name)
                          (task-find-agent-definition definitions name)))
                (json-get *workflow-catalog* "agents"))
               (passed "read-only-evaluator"
                       (equal (task-agent-definition-tools
                               (task-find-agent-definition definitions "evaluator"))
                              '("resource.read" "search.*")))
               (let ((instructions (task-agent-definition-instructions
                                    (task-find-agent-definition definitions "evaluator"))))
                 (passed "native-role-runtime-rendering"
                         (and (search "Workflow host: autolith" instructions)
                              (search (namestring *workflow-plugin-root*) instructions)))))
             (let* ((read-tool (tool-registry-find registry "resource" "read"))
                    (read-result (tool-execute read-tool context
                                               (json-object "uri" "workspace:.env")))
                    (edit-tool (tool-registry-find registry "resource" "edit"))
                    (edit-result (tool-execute edit-tool context
                                               (json-object "uri" "workspace:.env"))))
               (passed "env-read-blocked" (and (not (tool-result-success-p read-result))
                                               (tool-result-denied-p read-result)))
               (passed "env-edit-blocked" (and (not (tool-result-success-p edit-result))
                                               (tool-result-denied-p edit-result))))
             (let* ((shell-tool (tool-registry-find registry "shell" "run"))
                    (result (tool-execute shell-tool context
                                          (json-object "command" "git reset --hard"))))
               (passed "dangerous-git-blocked-before-native-execution"
                       (and (not (tool-result-success-p result))
                            (tool-result-denied-p result) (not authorized-p))))
             (let* ((read-tool (tool-registry-find registry "resource" "read"))
                    (reference (namestring (merge-pathnames "commands/spawn.md"
                                                           *workflow-plugin-root*)))
                    (result (tool-execute read-tool context (json-object "uri" reference))))
               (with-open-file (stream (concatenate 'string report ".reference.json")
                                       :direction :output :if-exists :supersede)
                 (write-line (json-encode
                              (json-object "success" (tool-result-success-p result)
                                           "content" (tool-result-content result))) stream))
               (passed "bundled-markdown-read-rendering"
                       (and (tool-result-success-p result)
                            (not authorized-p)
                            (search "spawn-session.sh implementer --host autolith"
                                    (tool-result-content result))
                            (not (search "${CLAUDE_PLUGIN_ROOT}" (tool-result-content result)))
                            (search "revision" (tool-result-content result)
                                    :test #'char-equal))))
             (let* ((read-tool (tool-registry-find registry "resource" "read"))
                    (reference (namestring (merge-pathnames "references/shared-patterns.md"
                                                           *workflow-plugin-root*)))
                    (result (tool-execute read-tool context
                                          (json-object "uri" reference "start-line" 1
                                                       "line-count" 50))))
               (passed "shared-reference-root-rendering"
                       (and (tool-result-success-p result)
                            (not authorized-p)
                            (search (namestring *workflow-plugin-root*)
                                    (tool-result-content result))
                            (not (search "${CLAUDE_PLUGIN_ROOT}"
                                         (tool-result-content result))))))
             (let* ((edit-tool (tool-registry-find registry "resource" "edit"))
                    (reference (namestring (merge-pathnames "commands/spawn.md"
                                                           *workflow-plugin-root*))))
               (passed "bundle-read-trust-does-not-authorize-edits"
                       (handler-case
                           (progn (tool-execute edit-tool context
                                               (json-object "uri" reference)) nil)
                         (tool-error () authorized-p))))
             (setf authorized-p nil)
             (let ((read-tool (tool-registry-find registry "resource" "read")))
               (passed "unlisted-package-files-retain-native-authorization"
                       (handler-case
                           (progn (tool-execute
                                   read-tool context
                                   (json-object "uri" (namestring
                                                       (merge-pathnames "README.md"
                                                                        *workflow-plugin-root*))))
                                  nil)
                         (tool-error () authorized-p))))
             (let* ((*workflow-correction-active-p* nil)
                    (*workflow-result-decisions* (make-hash-table :test #'eq)))
               (dotimes (attempt 3)
                 (passed (format nil "verification-repair-~D" (1+ attempt))
                         (not (agent-turn-complete-p
                               agent (workflow-smoke-result (format nil "fail-~D" attempt))))))
               (passed "verification-terminal-block"
                       (handler-case
                           (progn (agent-turn-complete-p agent (workflow-smoke-result "cap")) nil)
                         (agent-loop-error (condition)
                           (search "blocked" (autolith-error-message condition)
                                   :test #'char-equal))))
               (with-open-file (stream (merge-pathnames "accepted.flag" project)
                                       :direction :output :if-exists :supersede)
                 (write-line "accepted" stream))
               (let ((*workflow-correction-active-p* nil))
                 (passed "new-user-turn-retries-and-passes"
                         (agent-turn-complete-p agent (workflow-smoke-result "fixed"))))
               (delete-file (merge-pathnames "accepted.flag" project))
               (passed "source-change-invalidates-proof"
                       (not (agent-turn-complete-p agent (workflow-smoke-result "regression")))))
             (conversation-append-provider-metadata
              conversation '(:workflow-host-schema 1 :workflow-host-role "evaluator"))
             (passed "role-survives-resume"
                     (equal (workflow-restored-role conversation) "evaluator"))
             (let* ((*workflow-primary-role* (workflow-restored-role conversation))
                    (*workflow-primary-conversation* (conversation-identifier conversation))
                    (read-tool (tool-registry-find registry "resource" "read"))
                    (result (tool-execute read-tool context
                                          (json-object "uri" "workspace:.aws/config"))))
               (passed "resumed-evaluator-protects-secret-paths"
                       (and (not (tool-result-success-p result))
                            (tool-result-denied-p result)
                            (search "Evaluator" (tool-result-content result)))))
             (workflow-smoke-notifications #'passed configuration conversation registry agent project)
             (with-open-file (stream report :direction :output :if-exists :supersede
                                           :if-does-not-exist :create)
               (write-line (json-encode
                            (json-object "host" "autolith"
                                         "version" *autolith-version*
                                         "model_calls" 0 "criteria" criteria)) stream))
             t)
        (tool-registry-close-runtime-state registry)))))
