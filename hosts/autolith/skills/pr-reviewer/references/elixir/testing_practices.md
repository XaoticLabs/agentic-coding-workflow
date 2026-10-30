# Elixir Testing Best Practices

Comprehensive guidance for behavior-based testing in Elixir applications.

## Testing Philosophy

### Behavior Over Implementation
- Test **what** code does, not **how** it does it
- Focus on public APIs and observable behavior
- Avoid testing private functions directly
- Tests should survive refactoring

### Test Pyramid
```
      /\
     /  \  Integration (few)
    /____\
   /      \
  /  Unit  \ Unit (many)
 /  Tests  \
/___________\
```

- **Unit tests**: Most numerous, fast, isolated
- **Integration tests**: Moderate number, test interactions
- **End-to-end**: Few, test critical user flows

## ExUnit Fundamentals

### Test Organization

#### Module Structure
```elixir
defmodule MyApp.AccountsTest do
  use MyApp.DataCase, async: true

  alias MyApp.Accounts
  alias MyApp.Accounts.User

  describe "list_users/1" do
    test "returns all users when no filters" do
      user1 = insert(:user)
      user2 = insert(:user)

      assert Accounts.list_users() == [user1, user2]
    end

    test "filters by role" do
      admin = insert(:user, role: :admin)
      _guest = insert(:user, role: :guest)

      assert Accounts.list_users(role: :admin) == [admin]
    end
  end

  describe "create_user/1" do
    test "creates user with valid attributes" do
      attrs = %{email: "test@example.com", name: "Test User"}

      assert {:ok, %User{} = user} = Accounts.create_user(attrs)
      assert user.email == "test@example.com"
      assert user.name == "Test User"
    end

    test "returns error changeset with invalid attributes" do
      assert {:error, %Ecto.Changeset{}} = Accounts.create_user(%{})
    end
  end
end
```

#### Test Organization Principles
- **Use `describe` blocks**: Group related tests
- **One assertion per test**: Focus tests on a single behavior
- **Clear test names**: Describe the behavior being tested
- **Arrange-Act-Assert**: Structure tests clearly

### Async Testing

```elixir
# Async safe - no shared state
use MyApp.DataCase, async: true

# Not async safe - modifies global state, uses Mox in shared mode
use MyApp.DataCase, async: false
```

#### When to Use Async
- ✅ Tests that don't share state
- ✅ Tests with isolated database transactions
- ✅ Pure function tests
- ❌ Tests that modify global configuration
- ❌ Tests with shared mocks (non-private mode)
- ❌ Tests that rely on specific timing

## Testing Contexts

### Data Factories

#### Using ExMachina
```elixir
defmodule MyApp.Factory do
  use ExMachina.Ecto, repo: MyApp.Repo

  def user_factory do
    %MyApp.Accounts.User{
      email: sequence(:email, &"user#{&1}@example.com"),
      name: "User Name",
      role: :user,
      hashed_password: Bcrypt.hash_pwd_salt("password123")
    }
  end

  def admin_factory do
    struct!(
      user_factory(),
      %{role: :admin}
    )
  end

  def post_factory do
    %MyApp.Content.Post{
      title: "Post Title",
      body: "Post body content",
      user: build(:user),
      published_at: DateTime.utc_now()
    }
  end
end

# Usage in tests
user = insert(:user)
admin = insert(:admin)
post = insert(:post, user: user)
attrs = params_for(:user)
```

#### Factory Best Practices
- **Realistic data**: Factories should create valid, realistic data
- **Minimal attributes**: Only include required fields by default
- **Sequences**: Use sequences for unique fields (email, username)
- **Associations**: Build associations with `build/2`
- **Traits**: Use factory inheritance for variations

### Context Testing Patterns

#### Testing CRUD Operations
```elixir
describe "create_user/1" do
  test "creates user with valid data" do
    attrs = params_for(:user)
    assert {:ok, %User{} = user} = Accounts.create_user(attrs)
    assert user.email == attrs.email
  end

  test "requires email" do
    attrs = params_for(:user, email: nil)
    assert {:error, changeset} = Accounts.create_user(attrs)
    assert "can't be blank" in errors_on(changeset).email
  end

  test "requires unique email" do
    user = insert(:user)
    attrs = params_for(:user, email: user.email)

    assert {:error, changeset} = Accounts.create_user(attrs)
    assert "has already been taken" in errors_on(changeset).email
  end
end

describe "update_user/2" do
  test "updates user with valid data" do
    user = insert(:user)
    attrs = %{name: "New Name"}

    assert {:ok, %User{} = updated} = Accounts.update_user(user, attrs)
    assert updated.name == "New Name"
  end

  test "returns error with invalid data" do
    user = insert(:user)
    attrs = %{email: "not-an-email"}

    assert {:error, changeset} = Accounts.update_user(user, attrs)
    refute changeset.valid?
  end
end
```

#### Testing Queries
```elixir
describe "list_users/1" do
  test "returns users matching filters" do
    active_user = insert(:user, active: true)
    inactive_user = insert(:user, active: false)

    result = Accounts.list_users(active: true)

    assert active_user in result
    refute inactive_user in result
  end

  test "orders by name by default" do
    insert(:user, name: "Zoe")
    insert(:user, name: "Alice")

    [first, second] = Accounts.list_users()

    assert first.name == "Alice"
    assert second.name == "Zoe"
  end

  test "preloads associations when requested" do
    user = insert(:user)
    insert(:post, user: user)

    [loaded_user] = Accounts.list_users(preload: [:posts])

    assert Ecto.assoc_loaded?(loaded_user.posts)
  end
end
```

#### Testing Transactions
```elixir
describe "create_post_with_tags/2" do
  test "creates post and associated tags" do
    user = insert(:user)
    attrs = %{title: "Test", body: "Content"}
    tags = ["elixir", "testing"]

    assert {:ok, %{post: post, tags: tags}} =
      Content.create_post_with_tags(user, attrs, tags)

    assert post.title == "Test"
    assert length(tags) == 2
  end

  test "rolls back on error" do
    user = insert(:user)
    attrs = %{title: nil}  # Invalid
    tags = ["elixir"]

    assert {:error, :post, changeset, _changes} =
      Content.create_post_with_tags(user, attrs, tags)

    refute changeset.valid?
    assert Repo.aggregate(Tag, :count) == 0
  end
end
```

## Testing Controllers

### Request Testing
```elixir
defmodule MyAppWeb.UserControllerTest do
  use MyAppWeb.ConnCase

  describe "GET /users" do
    test "lists all users", %{conn: conn} do
      user = insert(:user)

      conn = get(conn, ~p"/users")

      assert html_response(conn, 200) =~ user.name
    end
  end

  describe "POST /users" do
    test "creates user and redirects when data is valid", %{conn: conn} do
      attrs = params_for(:user)

      conn = post(conn, ~p"/users", user: attrs)

      assert %{id: id} = redirected_params(conn)
      assert redirected_to(conn) == ~p"/users/#{id}"

      # Verify it was created
      assert Accounts.get_user!(id)
    end

    test "renders errors when data is invalid", %{conn: conn} do
      conn = post(conn, ~p"/users", user: %{email: nil})

      assert html_response(conn, 200) =~ "can&#39;t be blank"
    end
  end
end
```

### Authentication Testing
```elixir
describe "authentication" do
  setup %{conn: conn} do
    user = insert(:user)
    conn = log_in_user(conn, user)
    %{conn: conn, user: user}
  end

  test "requires authentication", %{conn: conn} do
    conn = delete(conn, ~p"/users/session")
    conn = get(conn, ~p"/users/settings")

    assert redirected_to(conn) == ~p"/users/log_in"
  end

  test "allows authenticated access", %{conn: conn, user: user} do
    conn = get(conn, ~p"/users/settings")

    assert html_response(conn, 200) =~ user.email
  end
end
```

## Testing LiveView

### Mount and Render Testing
```elixir
defmodule MyAppWeb.UserLive.IndexTest do
  use MyAppWeb.ConnCase
  import Phoenix.LiveViewTest

  describe "Index" do
    test "displays users", %{conn: conn} do
      user = insert(:user)

      {:ok, _view, html} = live(conn, ~p"/users")

      assert html =~ "Users"
      assert html =~ user.name
    end

    test "handles loading state", %{conn: conn} do
      {:ok, view, _html} = live(conn, ~p"/users")

      # Verify loading indicator disappears
      refute render(view) =~ "Loading..."
    end
  end
end
```

### Event Testing
```elixir
describe "form submission" do
  test "creates user on valid submission", %{conn: conn} do
    {:ok, view, _html} = live(conn, ~p"/users/new")

    result =
      view
      |> form("#user-form", user: params_for(:user))
      |> render_submit()

    assert result =~ "User created successfully"
    assert_redirect(view, ~p"/users")
  end

  test "displays errors on invalid submission", %{conn: conn} do
    {:ok, view, _html} = live(conn, ~p"/users/new")

    result =
      view
      |> form("#user-form", user: %{email: ""})
      |> render_submit()

    assert result =~ "can&#39;t be blank"
  end
end

describe "live navigation" do
  test "navigates to edit form", %{conn: conn} do
    user = insert(:user)
    {:ok, view, _html} = live(conn, ~p"/users")

    {:ok, view, html} =
      view
      |> element("#user-#{user.id} a", "Edit")
      |> render_click()
      |> follow_redirect(conn)

    assert html =~ "Edit User"
  end
end
```

### PubSub Testing
```elixir
describe "real-time updates" do
  test "updates on broadcast", %{conn: conn} do
    {:ok, view, _html} = live(conn, ~p"/users")

    user = insert(:user)
    Phoenix.PubSub.broadcast(
      MyApp.PubSub,
      "users",
      {:user_created, user}
    )

    # Wait for update to propagate
    assert render(view) =~ user.name
  end
end
```

## Mocking and Stubbing

### Using Mox

#### Setup
```elixir
# In test/test_helper.exs
Mox.defmock(MyApp.EmailMock, for: MyApp.Email.Behaviour)

# In config/test.exs
config :my_app, :email, MyApp.EmailMock
```

#### Usage in Tests
```elixir
defmodule MyApp.AccountsTest do
  use MyApp.DataCase
  import Mox

  setup :verify_on_exit!

  describe "create_user/1" do
    test "sends welcome email" do
      expect(MyApp.EmailMock, :send_welcome_email, fn user ->
        {:ok, user}
      end)

      attrs = params_for(:user)
      assert {:ok, user} = Accounts.create_user(attrs)
    end

    test "handles email failure gracefully" do
      stub(MyApp.EmailMock, :send_welcome_email, fn _user ->
        {:error, :smtp_error}
      end)

      attrs = params_for(:user)
      assert {:ok, user} = Accounts.create_user(attrs)
    end
  end
end
```

#### Mocking Best Practices
- **Use behaviors**: Define behaviors for mockable modules
- **Verify on exit**: Use `setup :verify_on_exit!`
- **Explicit expectations**: Use `expect/3` over `stub/3` when possible
- **Private mode**: Allow concurrent tests with `:set_mox_private`

## Testing Processes

### GenServer Testing
```elixir
defmodule MyApp.CacheTest do
  use ExUnit.Case, async: true

  test "stores and retrieves values" do
    {:ok, cache} = Cache.start_link([])

    :ok = Cache.put(cache, :key, :value)

    assert Cache.get(cache, :key) == :value
  end

  test "handles process crashes" do
    {:ok, cache} = Cache.start_link([])
    Process.unlink(cache)

    Cache.put(cache, :key, :value)
    Process.exit(cache, :kill)

    # Verify supervisor restarts process
    refute Process.alive?(cache)
  end
end
```

### Testing with Task
```elixir
describe "async operations" do
  test "processes items concurrently" do
    items = [1, 2, 3, 4, 5]

    results = MyApp.Worker.process_all(items)

    assert length(results) == 5
    assert Enum.all?(results, &match?({:ok, _}, &1))
  end

  test "handles task failures" do
    stub(MyApp.ExternalAPI, :fetch, fn _id ->
      {:error, :timeout}
    end)

    results = MyApp.Worker.process_all([1, 2])

    assert Enum.all?(results, &match?({:error, :timeout}, &1))
  end
end
```

## Test Data Management

### Database Setup
```elixir
# In test/support/data_case.ex
defmodule MyApp.DataCase do
  use ExUnit.CaseTemplate

  using do
    quote do
      alias MyApp.Repo
      import Ecto
      import Ecto.Changeset
      import Ecto.Query
      import MyApp.DataCase
      import MyApp.Factory
    end
  end

  setup tags do
    pid = Ecto.Adapters.SQL.Sandbox.start_owner!(MyApp.Repo, shared: not tags[:async])
    on_exit(fn -> Ecto.Adapters.SQL.Sandbox.stop_owner(pid) end)
    :ok
  end

  def errors_on(changeset) do
    Ecto.Changeset.traverse_errors(changeset, fn {message, opts} ->
      Regex.replace(~r"%{(\w+)}", message, fn _, key ->
        opts |> Keyword.get(String.to_existing_atom(key), key) |> to_string()
      end)
    end)
  end
end
```

### Test Isolation
```elixir
# Each test runs in a transaction
test "isolated test" do
  insert(:user)
  assert Repo.aggregate(User, :count) == 1
end

test "another isolated test" do
  # This starts with a clean database
  assert Repo.aggregate(User, :count) == 0
end
```

## Coverage and Quality

### Running Tests with Coverage
```bash
mix test --cover
```

### Coverage Best Practices
- **Aim for 80%+**: Good baseline for most projects
- **100% isn't always needed**: Focus on critical paths
- **Test behavior**: Don't just chase coverage numbers
- **Ignore generated code**: Exclude migrations, schemas

### Test Organization
```
test/
├── my_app/
│   ├── accounts/
│   │   ├── user_test.exs
│   │   └── policy_test.exs
│   ├── accounts_test.exs
│   └── content_test.exs
├── my_app_web/
│   ├── controllers/
│   │   └── user_controller_test.exs
│   ├── live/
│   │   └── user_live_test.exs
│   └── views/
│       └── user_view_test.exs
└── support/
    ├── channel_case.ex
    ├── conn_case.ex
    ├── data_case.ex
    └── factory.ex
```

## Common Testing Anti-Patterns

1. **Testing private functions**: Test public API instead
2. **Brittle tests**: Tests that break on refactoring
3. **Shared state**: Tests that depend on execution order
4. **No factories**: Using raw maps/structs instead of factories
5. **Testing implementation**: Asserting on internals instead of behavior
6. **Slow tests**: Not using async, not using test database
7. **No edge cases**: Only testing happy path
8. **Mock everything**: Over-mocking makes tests meaningless
9. **Large setup blocks**: Setup should be minimal
10. **No test descriptions**: Unclear what's being tested

## Advanced Testing Patterns

### Property-Based Testing
```elixir
use ExUnitProperties

property "list_users always returns a list" do
  check all filter <- optional_map(boolean()),
            max_runs: 100 do
    result = Accounts.list_users(filter)
    assert is_list(result)
  end
end
```

### Testing Race Conditions
```elixir
test "handles concurrent updates" do
  user = insert(:user, balance: 100)

  tasks =
    for _ <- 1..10 do
      Task.async(fn ->
        Accounts.withdraw(user.id, 10)
      end)
    end

  results = Task.await_many(tasks)

  user = Accounts.get_user!(user.id)
  assert user.balance == 0
  assert Enum.count(results, &match?({:ok, _}, &1)) == 10
end
```

### Integration Testing
```elixir
test "complete user signup flow" do
  # Register
  {:ok, user} = Accounts.register_user(params_for(:user))

  # Verify email sent
  assert_receive {:email_sent, ^user}

  # Confirm email
  {:ok, token} = Accounts.create_confirmation_token(user)
  {:ok, confirmed_user} = Accounts.confirm_user(token)

  # Log in
  assert {:ok, _session} = Accounts.create_session(confirmed_user)
end
```
