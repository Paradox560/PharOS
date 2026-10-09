# Team 8 workshop deployment

Prepared for the official no-registry deployment path. **No deployment has been applied.** The application runs at `/app` on Team 8's existing ingress. Humans enter through [the workshop](https://workshop.thecosmoslabs.com) → **App**; `INGRESS_URL` is a server-side API address.

## Package for review

```bash
.venv/bin/python scripts/prepare_deploy.py --team team-8
```

This writes `deploy/generated/pharos.json` and `package-report.json` (both ignored by Git). The current package is about 292 KB encoded, below its enforced 900,000-byte ceiling. The ConfigMap contains compressed application source, exact frontend lockfiles, verified catalog sample and a small versioned SUMO network. It excludes credentials, media, node_modules, compiled frontend bundles, discovery screenshots and run outputs.

An unpack init container extracts code to a workspace volume. A Node init container installs the locked frontend dependencies and builds with `--base=/app/`. A Python init container installs pinned API/SUMO dependencies into a runtime volume and verifies `sumo --version`. A source checksum in the pod template triggers replacement and rebuilding when the packaged code changes. The runtime serves assets, API, SSE and Range-capable media at internal `/`; nginx strips `/app`. The original VSS `/api/v1` routes are unchanged.

Required environment capabilities still need verification on the assigned cluster: public images, npm/PyPI egress, compatible Linux SUMO wheels, image pull policy, namespace quotas, and storage access. The manifest intentionally fails initialization if runtime installation fails rather than substituting fake simulations.

`/data` uses `emptyDir` by default and is **lost when the pod is replaced**. For durable application state, pass `--pvc <existing-approved-team-claim>`. No PVC or infrastructure is provisioned by the packager. VAST application artifact storage is not assumed: outputs remain in local application storage until an approved separate team destination exists.

## Private configuration on the assigned VM

Use the preconfigured Team 8 environment. If required variables are absent, inspect only `/config/team-8.config`; never search other teams. Prefer `/config/kubeconfig` or the explicit `/config/team-8-k8s.yaml` alias if the former does not exist. Check `USERNAME=team-8` before any resource operation.

The generated deployment requires a separate operator password so it cannot expose the shared archive or inference quota to anonymous callers. Set `PHAROS_OPERATOR_USERNAME` (default `operator`) and `PHAROS_OPERATOR_PASSWORD` privately in the VM's environment. The browser uses HTTP Basic over the workshop's HTTPS entry. The password is server-side, never compiled into assets; health probes are the only unauthenticated API.

```bash
python3 scripts/prepare_workshop_secret.py --team team-8
```

This creates `/tmp/pharos-workshop-secret.json` with mode `0600`, refuses overwrite, and prints no values. Do not commit it. `WANDB_MODEL` must be selected from the actual provider's model catalog. Optional Weave tracing is disabled in the generated runtime; enabling it requires an explicitly pinned/tested Weave installation and environment flag, separately from working W&B inference.

## Apply only after deployment authorization

After reviewing the exact manifests and confirming Team 8 access/resources:

```bash
pharos_kubeconfig=/config/kubeconfig
if [ ! -f "$pharos_kubeconfig" ]; then pharos_kubeconfig=/config/team-8-k8s.yaml; fi
test -f "$pharos_kubeconfig" || exit 1
kubectl --kubeconfig "$pharos_kubeconfig" -n team-8 apply -f /tmp/pharos-workshop-secret.json
kubectl --kubeconfig "$pharos_kubeconfig" -n team-8 apply -f deploy/generated/pharos.json
kubectl --kubeconfig "$pharos_kubeconfig" -n team-8 rollout status deployment/pharos --timeout=600s
kubectl --kubeconfig "$pharos_kubeconfig" -n team-8 get pods,services,ingresses -l app=pharos
```

Verify authenticated HTML, `/app/assets/*`, `/app/api/health`, real archive inventory, video HTTP 206 seeking, SSE, and a complete CPU scenario run. Verify the 401 response for unauthenticated archive/media requests. Open the workshop **App** entry to check real ingress behavior. Local tests are not a substitute for these cluster checks.

Re-ingestion remains disabled after deployment. Enable it only for one designated owner after a concrete one-chunk preview is reviewed, with the selected target, prompt, preserved metadata and chunk count confirmed. The provided model graph remains untouched.
