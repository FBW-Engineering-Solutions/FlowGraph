---
id: reference.adapters.table-tools
title: Table Tool Nodes
section: Reference
order: 23
description: Nodes for constructing table documents from workflow lists.
---

# Table tool nodes

## Aggregate Lists to Table (`aggregate-lists-to-table`)

Connect one or more list outputs to expandable `column` input ports. The node
supports up to 128 list inputs and produces `table: Table document`, a mapping
whose column names come from the *source output port names* of the connections.
It keeps an unconnected spare input while below capacity. Lists must have equal
lengths, and source output port names must be unique: duplicate names, unequal
lengths, and an empty set of connections are errors. The node has no parameters.

Connect the resulting table to [Plot Table](sinks.md),
[Write Table (Pandas)](writers.md), or a workflow output.