# S3 review for issues 16 and 23

Reviewed on September 29, 2026. This is an internal operations note; the [deployment guide](../docs/admin/deployment.md) contains the supported setup for new buckets.

## Issue 23: non-East bucket URLs

The app already read `AWS_S3_REGION_NAME`, but boto3 generated a global-host presigned URL for `us-west-2` in a local test. The S3 client now requests Signature Version 4 and virtual-host addressing for AWS, so the signed host and credential scope both use the configured region. Custom endpoints such as LocalStack retain path-style addressing.

Live verification used the app's `S3UploadHandler` with temporary credentials against `efile-form-submission` in `us-east-2`. A temporary PDF uploaded successfully; its regional presigned URL returned the same bytes with HTTP 200, its unsigned URL returned HTTP 403, and deletion succeeded. This verifies a private-bucket download without changing any bucket policy. The proxy's document deserializer uses an ordinary HTTP GET, so the same URL format is usable there. See [issue 23](https://github.com/SuffolkLITLab/LITEFile/issues/23).

## Issue 16: current exposure and permissions

The `litefile-staging` bucket is in `us-east-1`. At review time its policy granted `s3:GetObject` to `Principal: "*"`, all four bucket-level Block Public Access settings were off, and AWS reported `IsPublic: true`. It has Bucket owner enforced object ownership. The Fly.io `litefile-staging` app uses this bucket and the IAM user `efile-form-submission`. A temporary object uploaded, downloaded through that user's direct S3 access and a presigned URL, and was deleted successfully. The bucket does not need a public-read policy for this app's normal URL path. S3 server access logging is not configured on this bucket, so that source cannot identify other clients using unsigned URLs. See [issue 16](https://github.com/SuffolkLITLab/LITEFile/issues/16) and [AWS presigned URL documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html).

The attached IAM policy `efile-form-submission-bucket-access` still grants `s3:PutObjectAcl` on objects and `s3:*` on the bucket ARNs for `efile-form-submission`, `efile-form-submission-bucket`, `litefile-staging`, and `litefile-suffolk`. The same principal is used by staging, and the policy spans four buckets, so replacing it with a one-bucket policy without checking other users of those credentials could interrupt another workflow. The narrower policy in the README and deployment guide describes the permissions this app uses: list only the document prefix, and put, get, delete, and abort multipart uploads only within that prefix. `s3:PutObjectAcl` is unnecessary because the app does not set object ACLs.

The `efile-form-submission` bucket is in `us-east-2`, with all four Block Public Access settings on. Its retained public-read policy makes AWS report `IsPublic: true` despite those blocks. `efile-form-submission-bucket` has the same policy and block combination. Those policies are unnecessary for the verified presigned flow, but their removal should be evaluated with each bucket's other consumers.

## Staging changes completed

The signing change was deployed to `litefile-staging` as image `litefile-staging:deployment-01M3QHA7H2FHN0F4H5CQ69FBGJ`. The deployed app uploaded and deleted a temporary PDF. Its presigned GET returned HTTP 200 and an unsigned GET returned HTTP 403. All four staging bucket Block Public Access settings were enabled and the `PublicReadGetObject` policy was removed. AWS now returns `NoSuchBucketPolicy` for that bucket. The signed and unsigned checks were repeated after the policy removal with the same results.

An Illinois Adams County adoption complaint was then filed end to end through the staging browser and Tyler test EFSP using synthetic PDFs and the test account's fee waiver path. Playwright passed, the confirmation page appeared, and staging draft `95` was saved as `submitted` on September 29, 2026 at 22:06 UTC. The Tyler response contained two filing IDs, one for each submitted document. A preceding paid attempt reached Tyler but returned `Payment declined`; that draft `93` is `error`, with no submission timestamp. Two earlier interrupted attempts remained drafts. The successful filing verifies the deployed private S3 document URL in the EFSP submission path. During the browser tests, staging document extraction logged an Azure OpenAI HTTP 401; the filing completed through the manual document review path, so extraction needs its own credential check.

The Docker build context now excludes `court_forms/` (about 1.9 GB locally). The deployed image is about 219 MB and has no `/app/court_forms` directory. The crosswalk review route is disabled in staging (`/review/` returns HTTP 404). The `litefile-crosswalk-review` Machine `8654509b432518` was stopped and its Fly service has `auto_start_machines = false`.

## Remaining IAM work

The shared IAM principal still has broad permissions across four buckets. Give staging its own principal or verify every consumer of the current principal before reducing that policy. Scope the resulting policy to the document prefix as described in the deployment guide. The public-read policies retained on the other two buckets also need a separate consumer audit. The staging bucket policy change may break any unknown client that depended on an unsigned object URL; S3 access logging was off, so historical consumers could not be enumerated from that source.
