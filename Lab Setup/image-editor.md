# ImageFlow Vulnerable Image Processing Lab

## Overview

ImageFlow is an intentionally vulnerable image-processing application designed for SOC analyst, threat hunting, and detection engineering practice.

The application accepts image uploads, stores them on disk, and allows users to apply image-processing operations through a separate processing service. The environment is specifically designed to generate realistic telemetry for tools such as Elastic Security, SIEM platforms, EDR solutions, and endpoint monitoring products.

You can find the app in the ```ImageFlow``` directory

---

## Security Features Implemented

The upload component includes several security controls commonly found in real-world applications:

* Extension allowlisting (`.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.bmp`)
* Magic-byte validation
* UUID-based file renaming
* Upload size restrictions
* Separate plugin-upload functionality
* AST-based validation for uploaded Python plugins

These controls are intentionally included to demonstrate an important security lesson:

> A system can contain multiple security controls and still be vulnerable if trust assumptions are incorrect.

---

## Intentional Vulnerability

The primary vulnerability exists in the image-processing service.

When a user uploads an image, the application validates the file type and stores it on disk. Later, when image processing is requested, the file is passed to the processing service.

The service attempts to open the file using Pillow:

1. Open image
2. Verify image structure
3. Apply image enhancements
4. Save processed output

Under normal circumstances this workflow is safe.

However, if Pillow cannot parse the uploaded file as a valid image, the application follows an unsafe fallback path.

Instead of rejecting the file and returning an error, the processing service assumes the user may have accidentally submitted a Python plugin to the image-processing endpoint.

The application therefore attempts to execute the file as Python code.

This decision creates a dangerous trust boundary violation:

* Upload validation occurs only once.
* Runtime validation is skipped.
* Any file that reaches the processing stage is implicitly trusted.
* The processing service executes content that was never intended to be executed.

The core design flaw is not the upload validation itself.

The flaw is the assumption that:

> "If the upload passed validation earlier, it must be safe to execute later."

This assumption is incorrect and is the root cause of the vulnerability.

---

## Educational Goals

The lab is intended to help students understand:

* File upload security
* Trust boundary failures
* Runtime validation mistakes
* Secure software design principles
* Process creation telemetry
* Endpoint detection engineering
* SOC investigation workflows
* Attack chain reconstruction

The focus of the exercise is detection and response rather than exploitation.

Participants are encouraged to investigate:

* File creation events
* Process execution events
* Parent-child process relationships
* Network activity
* Alert generation
* Incident timelines

using Elastic Security and related monitoring tools.

---

## Why This Application Is Dangerous

Running this application on a network accessible to untrusted users may allow uploaded content to be executed by the processing service.

As a result:

* Arbitrary code execution may occur.
* The application host may be compromised.
* Additional malware may be installed.
* Persistence mechanisms may be deployed.
* Other systems on the network may be targeted.

For these reasons:

* Deploy only inside isolated lab environments.
* Do not expose the application to the public Internet.
* Do not store sensitive information on the host.
* Do not run the application with elevated privileges.
* Treat the machine as intentionally vulnerable.

---

## Intended Usage

This project exists solely for cybersecurity education, detection engineering practice, incident response exercises, and SOC analyst training.

It should be considered a deliberately insecure application whose purpose is to generate realistic attack telemetry for defensive analysis.

