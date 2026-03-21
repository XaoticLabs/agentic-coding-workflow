# Elixir/OTP Best Practices

Key patterns and principles from "Elixir in Action" and OTP design guidelines.

## Process Design

### GenServer Patterns
- **Separation of interface and implementation**: Public API functions should delegate to `GenServer.call/cast`
- **Handle all callbacks**: Always implement `handle_info/2` to prevent crashes from unexpected messages
- **Timeout handling**: Use `:timeout` option in `GenServer.call` for operations that might hang
- **State management**: Keep state minimal and well-structured; consider using structs for complex state

```elixir
# Good - Clear interface
def get_value(pid, key) do
  GenServer.call(pid, {:get, key})
end

# Implementation
def handle_call({:get, key}, _from, state) do
  {:reply, Map.get(state, key), state}
end

# Always handle unexpected messages
def handle_info(_msg, state) do
  {:noreply, state}
end
```

### Process Lifecycle
- **Start functions**: Provide `start_link/1` for supervision tree integration
- **Initialization**: Keep `init/1` fast; use `handle_continue/2` for heavy initialization
- **Shutdown**: Implement proper cleanup in `terminate/2` when needed
- **Child specs**: Implement `child_spec/1` for flexible supervision

### State Management
- **Immutability**: Never mutate state directly; always return new state
- **Data structures**: Use appropriate data structures (Map for lookups, List for sequential access)
- **Avoid bloating**: Don't store derived data; compute on demand or cache appropriately

## Supervision Trees

### Supervision Strategies
- **one_for_one**: Default choice; restart only failed child
- **one_for_all**: Use when children are interdependent
- **rest_for_one**: Use for sequential dependencies
- **Strategy selection**: Choose based on actual dependencies, not convenience

### Supervisor Design
- **Layered supervision**: Build supervision trees in layers, don't flatten
- **Error kernel**: Keep critical state in supervised processes
- **Let it crash**: Don't defensively handle every error; let supervisors handle failures
- **Restart intensity**: Configure `:max_restarts` and `:max_seconds` appropriately

```elixir
# Good - Layered supervision
def init(_) do
  children = [
    {CacheManager, []},
    {WorkerSupervisor, []},
    {DatabasePool, []}
  ]

  Supervisor.init(children, strategy: :one_for_one)
end
```

## Concurrency Patterns

### Message Passing
- **Synchronous vs Asynchronous**: Use `call` for operations needing replies, `cast` for fire-and-forget
- **Message structure**: Use tagged tuples for clarity: `{:get, key}` not just `key`
- **Response patterns**: Be consistent with reply formats

### Task Management
- **Task.async/await**: Use for concurrent computations with bounded lifetimes
- **Task.Supervisor**: Use for dynamic task spawning with supervision
- **Avoid Task.start**: Prefer supervised alternatives

### Agent Usage
- **Simple state**: Use Agent for simple stateful wrappers
- **Not for logic**: Don't put complex logic in Agent callbacks
- **Consider alternatives**: For complex state, use GenServer

## Error Handling

### Let It Crash Philosophy
- **Don't catch everything**: Only handle errors you can meaningfully recover from
- **Supervision for recovery**: Let supervisors restart failed processes
- **Defensive vs offensive**: Write offensive code; let the system heal

### Error Propagation
- **Link chains**: Understand process links and monitors
- **Task errors**: Be aware that linked tasks propagate exits
- **Try/rescue**: Use sparingly; prefer pattern matching on {:ok, result} | {:error, reason}

```elixir
# Good - Pattern match on results
case File.read(path) do
  {:ok, content} -> process(content)
  {:error, reason} -> handle_error(reason)
end

# Avoid defensive code
try do
  do_something()
rescue
  _ -> :ok  # Bad - swallowing all errors
end
```

## Code Organization

### Module Design
- **Single responsibility**: One module, one purpose
- **Public API**: Clear separation between public and private functions
- **Function length**: Keep functions short and focused (< 10 lines ideal)
- **Nested modules**: Use for namespacing related functionality

### Function Design
- **Pattern matching**: Use function heads for different cases
- **Guards**: Prefer guards over if/case when possible
- **Pipe operator**: Use for data transformations, but don't overdo it
- **Anonymous functions**: Prefer named functions for clarity

```elixir
# Good - Pattern matching in function heads
def process(%User{role: :admin} = user), do: grant_access(user)
def process(%User{role: :guest} = user), do: limited_access(user)

# Good - Guards
def calculate(x) when is_number(x) and x > 0 do
  # ...
end
```

## Data Structures

### Choosing the Right Structure
- **Map**: Fast key-value lookups (O(log n))
- **Keyword list**: Small collections where order matters, duplicate keys needed
- **Struct**: When enforcing a schema/shape on data
- **ETS**: Large datasets, fast lookups, shared across processes

### Struct Best Practices
- **Always define keys**: Don't rely on dynamic fields
- **Default values**: Provide sensible defaults
- **Enforce keys**: Use `@enforce_keys` for required fields
- **Documentation**: Document the purpose of each field

```elixir
defmodule User do
  @enforce_keys [:id, :email]
  defstruct [:id, :email, role: :guest, active: true]
end
```

## Performance Considerations

### Avoid Premature Optimization
- **Measure first**: Use profiling tools before optimizing
- **Hot paths**: Focus on frequently called code
- **Avoid**: Micro-optimizations that hurt readability

### Common Optimizations
- **Tail call optimization**: Ensure recursive functions are tail-recursive
- **Lazy evaluation**: Use Stream for large collections
- **Avoid string concatenation**: Use IO lists or interpolation
- **Process dictionary**: Avoid; use proper state management

### Bottlenecks
- **GenServer serialization**: Don't make GenServer a bottleneck; distribute load
- **Process mailbox**: Monitor mailbox size; use backpressure
- **Database calls**: Batch operations, use indexes, preload associations

## Testing

### Test Structure
- **Describe/test blocks**: Use ExUnit's describe for grouping
- **Setup callbacks**: Use setup/setup_all for test preparation
- **Async tests**: Use `async: true` when tests don't share state

### Process Testing
- **Isolation**: Tests should start/stop their own processes
- **Synchronization**: Use Process.sleep sparingly; prefer synchronous operations
- **Assertions**: Test behavior, not implementation details

```elixir
# Good - Testing behavior
test "cache stores and retrieves values" do
  {:ok, cache} = Cache.start_link([])
  :ok = Cache.put(cache, :key, :value)
  assert Cache.get(cache, :key) == :value
end
```

## Documentation

### Module Documentation
- **@moduledoc**: Always provide; explain purpose and usage
- **Examples**: Include usage examples in moduledoc
- **@doc**: Document all public functions
- **@spec**: Provide type specifications for public functions

### Code Comments
- **Why, not what**: Explain reasoning, not obvious operations
- **Complex logic**: Comment non-obvious algorithms
- **TODOs**: Track technical debt with TODO comments

## Common Anti-Patterns to Avoid

1. **Over-using processes**: Not everything needs to be a process
2. **Process dictionary abuse**: Avoid; use proper state management
3. **Catching all errors**: Let it crash; don't swallow errors
4. **Blocking GenServer calls**: Keep GenServer handlers fast
5. **Large message passing**: Avoid passing large data structures between processes
6. **Premature abstraction**: Write concrete code first, abstract later
7. **Ignoring backpressure**: Monitor and handle message queue growth
8. **Synchronous initialization**: Use `handle_continue/2` for heavy init
9. **Tight coupling**: Keep modules independent and loosely coupled
10. **Stateful modules**: Prefer functional approaches; use processes only when needed
