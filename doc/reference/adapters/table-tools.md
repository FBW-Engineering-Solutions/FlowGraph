---
id: reference.adapters.table-tools
title: Table Tool Nodes
section: Reference
order: 23
description: Nodes for constructing table documents from workflow lists or mesh fields.
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

## Mesh to Table (`mesh-to-table`)

Accepts `mesh: Mesh document` and produces `table: Table`. The internal **Data
location** selector chooses **Node data** (default) or **Cell data**; it is not
an input port. Each field in the selected `nodeFields` or `elemFields` collection
becomes a table column, with one row per node or cell. This includes the mesh
document's generated `flowgraph_node_id` or `flowgraph_element_id` field.
Multi-component fields retain their components as a list in each row. Coordinates,
connectivity, and fields from the other entity type are not included. The source
mesh is unchanged; fields with a row count different from the selected entity
count raise an error.