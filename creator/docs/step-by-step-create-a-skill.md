# Step by step SKILL creation

This document describes the process of building a new skill in skills-for-fabric.  
It describes, step by step, how to apply the best practices.  
For the purpose of this document, imagine you are building a consumption skill for an engine called YOURENGINE.  
Therefore, respecting the convention, the skill will be named *yourengine-consumption-cli*. This name will be used as a placeholder in the rest of the document.

## Table of Contents
- [Step 1: Create your first draft](#step-1-create-your-first-draft)
- [Step 2: Look for SKILL description conflicts](#step-2-look-for-skill-description-conflicts)
- [Step 3: Cleanup the CORE document](#step-3-cleanup-the-core-document)
- [Step 4: Refactor actual skill](#step-4-refactor-actual-skill)
- [Step 5: Compact the skill](#step-5-compact-the-skill)
- [Step 6: TOC consistency check](#step-6-toc-consistency-check)

## Step 1: Create your first draft
Per the current convention, you may want to create the following:

### YOURENGINE-CONSUMPTION-CORE document
This is a document stored in the [../common](../common) folder.
The purpose of the document is to describe the core consumption concepts for the YOURENGINE engine.  
Look at examples, such as [../common/SQLDW-CONSUMPTION-CORE.md](../common/SQLDW-CONSUMPTION-CORE.md).

> **IMPORTANT**
> Use proper L2 headings (##) for important concepts, use L3 (###) for sub-concepts.
> Use the proper keywords in the titles (this will be very important later).

### The actual skill
* Under /skills, create a *yourengine-consumption-cli* folder
* Underneath, create a SKILL.md document
* [Optional] create a resources folder
* Respect the skill format (documented elsewhere)
* Use proper L2 headings (##) for important concepts, use L3 (###) for sub-concepts.
* Use the proper keywords in the titles (this will be very important later).

You can use Github Copilot CLI itself to generate a skill. Example prompt:
* EXAMPLE PROMPT:
```text
Create a new skill called yourengine-consumption-cli. Use the standard and best practices in this repo. Look at http://learn.microsoft.com/YOURENGINE for concepts and APIs. Be concise, avoid duplication. Use the sql-consumption-cli as an example. Keep the SKILL.md itself relatively small. If a subtopic is too detailed, describe it in an individual article in the resources folder, and add a reference inside the SKILL.md document.
```

* [Optional]
Create other reference topic articles under resources.

## Step 2: Look for SKILL description conflicts
Use the following to identify skill description conflicts:
* EXAMPLE PROMPT:
```text
Traverse all the skills (/skill/**/SKILL.md). Look at their descriptions, and compare each of them with yourengine-consumption-cli's description. Highlight the keywords which create ambiguity between the respective skill and yourengine-consumption-cli
```
Now fix as much as you can from the conflicts


## Step 3: Cleanup the CORE document

> IMPORTANT -- Edit AGENTS.md from the root folder and remove the restrictions contained by these lines (agents are not allowed to write in core):
>
>  Copilot can read the common folder, but *can never write* inside the common folder.  
>  The files under /common should only be modified manually


Use the following to clean up you CORE document:
* EXAMPLE PROMPT:
```text
review the YOURENGINE-CONSUMPTION-CORE.md document. Remove redundant information, increase clarity and, perhaps, reduce token cost. Also please validate if any references from other md documents (including the TOC from yourengine-consumption-cli) need update and update them as well.
```
> IMPORTANT -- Revert the above changes to the AGENTS.md file.
>  
> REVIEW THE CHANGES TO THE DOCUMENT

## Step 4: Refactor actual skill
Use the following to refactor your actual skill:
* EXAMPLE PROMPT (the update check part and the critical notes are needed only if not there already, e.g. if you created the skill using the skill to create the skills they will already be there):
```text
I want you to refactor the yourengine-consumption-cli skill.
 
First, after the yaml of the skill, print the following:
 
> **Update Check — ONCE PER SESSION (mandatory)**	
> The first time this skill is used in a session, run the **check-updates** skill before proceeding.
> - **GitHub Copilot CLI / VS Code**: invoke the `check-updates` skill.
> - **Claude Code / Cowork / Cursor / Windsurf / Codex**: compare local vs remote package.json version.
> - Skip if the check was already performed earlier in this session.

> **CRITICAL NOTES**
> 1. To find the workspace details (including its ID) from workspace name: list all workspaces and, then, use JMESPath filtering
> 2. To find the item details (including its ID) from workspace ID, item type, and item name: list all items of that type in that workspace and, then, use JMESPath filtering
 
Then, I want the skill to be a TOC - literally like a document index with the header:
  - Task
  - Reference
  - Notes (for any core instructions, such as *MUST READ* or so, but also for all ### titles)
 (Follow the pattern from the sqldw-consumption-cli skill)
The rows:
	Traverse the sections inside the common/common-core . For each major section (all identified by ##), generate a row inside the TOC of the yourengine-consumption-cli with the columns:
  - Task - <section name>
  - Reference - [COMMON-CORE.md](../../common/COMMON-CORE.md) <section name>
	similar for common/common-cli
 
	similar for YOURENGINE-CONSUMPTION-CORE.md
 
	similar for each file under resources (if any)
Lastly, take all the topics currently inside yourengine-consumption-cli which are not covered by the steps above, leave them inline in the yourengine-consumption-cli and put for each of the ## topic a row in the TOC with the reference to the section within this very document yourengine-consumption-cli (at the respective section name)

```
> REVIEW THE CHANGES TO THE DOCUMENT

## Step 5: Compact the skill
Use the following prompt to compact your skill:
* EXAMPLE PROMPT:
```text
Look at yourengine-consumption-cli skill (*and* at its child documents in its references or resources folders). The ## sections appear as references in TOCs in skills (e.g. in yourengine-consumption-cli/SKILL.md). In the interest of minimizing as much as possible the TOCs (but **WITHOUT** reducing the quality of the LLM processing), think if it makes sense to change the categories of some ## to ### (coalescing some ## - such that still the ## sections make sense but the number of them decreases). if you do that, make sure that the ### titles appear in the TOC notes (to be found). Again make sure the quality of the LLM processing would **NOT** decrease. *If* any such changes were operated, please recalculate the references to this file (from TOCs of skills or any other reference) and update such that everything checks out.
```
> REVIEW THE CHANGES TO THE DOCUMENT

## Step 6: TOC consistency check
Use the following prompt to ensure the structure of your TOC
* EXAMPLE PROMPT:
```text
Review now skills/yourengine-consumption-cli, the skill's resources folder, as well as core/YOURENGINE-CONSUMPTION-CORE.
I want references to point from skill to (common or resources), or from resources to (common), but never in the other direction
Make sure that:
- all headings 2 in the core document are reflected in the TOC
- all headings 2 in the skill resources document are reflected in the TOC
- no heading 3 is reflected in the skill's TOC
- all references in the TOC are valid
```