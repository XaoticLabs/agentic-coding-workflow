# Modern Ecto and Phoenix Patterns

Best practices for working with Ecto and Phoenix in modern Elixir applications.

## Ecto Best Practices

### Schema Design

#### Struct-Based Schemas
```elixir
defmodule MyApp.Accounts.User do
  use Ecto.Schema
  import Ecto.Changeset

  @primary_key {:id, :binary_id, autogenerate: true}
  @foreign_key_type :binary_id

  schema "users" do
    field :email, :string
    field :name, :string
    field :role, Ecto.Enum, values: [:user, :admin]
    field :password, :string, virtual: true, redact: true
    field :hashed_password, :string, redact: true

    has_many :posts, MyApp.Content.Post
    has_many :comments, MyApp.Content.Comment

    timestamps()
  end
end
```

#### Key Principles
- **Use UUIDs**: Prefer `:binary_id` primary keys for distributed systems
- **Ecto.Enum**: Use for fixed value sets instead of strings
- **Virtual fields**: Use for temporary data (like passwords before hashing)
- **Redaction**: Mark sensitive fields with `redact: true`
- **Timestamps**: Always include `timestamps()` for audit trails

### Changesets

#### Changeset Structure
```elixir
def changeset(user, attrs) do
  user
  |> cast(attrs, [:email, :name, :password])
  |> validate_required([:email, :name])
  |> validate_format(:email, ~r/@/)
  |> validate_length(:password, min: 8)
  |> unique_constraint(:email)
  |> put_password_hash()
end
```

#### Changeset Best Practices
- **Separate changesets**: Create specific changesets for different operations (registration vs update)
- **Validation order**: Run cheap validations first, expensive ones last
- **Custom validations**: Extract complex validations into named functions
- **Error messages**: Provide clear, user-friendly error messages
- **avoid validate_change when possible**: Prefer specific validators

#### Named Changesets
```elixir
def registration_changeset(user, attrs) do
  user
  |> cast(attrs, [:email, :password])
  |> validate_required([:email, :password])
  |> validate_confirmation(:password, required: true)
  |> put_password_hash()
end

def update_profile_changeset(user, attrs) do
  user
  |> cast(attrs, [:name, :bio])
  |> validate_required([:name])
end
```

### Queries

#### Query Organization
```elixir
defmodule MyApp.Accounts do
  import Ecto.Query

  # Public API
  def list_active_users do
    User
    |> active()
    |> order_by_name()
    |> Repo.all()
  end

  # Query fragments (private)
  defp active(query) do
    where(query, [u], u.active == true)
  end

  defp order_by_name(query) do
    order_by(query, [u], u.name)
  end
end
```

#### Query Best Practices
- **Composable queries**: Build queries from small, reusable fragments
- **Avoid N+1**: Always use `preload` or joins for associations
- **Use dynamic queries**: For complex filtering, use `Ecto.Query.dynamic/2`
- **Limit results**: Always paginate or limit large result sets
- **Named bindings**: Use named bindings for complex joins

#### Preloading Associations
```elixir
# Good - Single query with join
posts =
  Post
  |> join(:inner, [p], u in assoc(p, :user))
  |> preload([p, u], user: u)
  |> Repo.all()

# Good - Separate queries (when association is large)
posts = Repo.all(Post) |> Repo.preload(:user)

# Bad - N+1 queries
posts = Repo.all(Post)
Enum.map(posts, & &1.user)  # This triggers one query per post
```

### Transactions

#### Transaction Patterns
```elixir
# Good - Multi pattern for explicit steps
def create_post_with_tags(post_attrs, tag_names) do
  Ecto.Multi.new()
  |> Ecto.Multi.insert(:post, Post.changeset(%Post{}, post_attrs))
  |> Ecto.Multi.run(:tags, fn repo, %{post: post} ->
    create_tags(repo, post, tag_names)
  end)
  |> Repo.transaction()
end

# Good - Simple transaction
def transfer_balance(from, to, amount) do
  Repo.transaction(fn ->
    with {:ok, _} <- withdraw(from, amount),
         {:ok, _} <- deposit(to, amount) do
      :ok
    else
      {:error, reason} -> Repo.rollback(reason)
    end
  end)
end
```

#### Transaction Best Practices
- **Use Multi**: Prefer `Ecto.Multi` for complex, multi-step transactions
- **Keep short**: Minimize work inside transactions
- **Error handling**: Use `Repo.rollback/1` to abort transactions
- **Avoid side effects**: No HTTP calls, file I/O, or external services in transactions

### Repository Patterns

#### Context-Based Repositories
```elixir
defmodule MyApp.Accounts do
  alias MyApp.Repo
  alias MyApp.Accounts.User

  # List operations
  def list_users(opts \\ []) do
    User
    |> apply_filters(opts)
    |> Repo.all()
  end

  # Get operations
  def get_user!(id), do: Repo.get!(User, id)
  def get_user_by_email(email), do: Repo.get_by(User, email: email)

  # Create operations
  def create_user(attrs) do
    %User{}
    |> User.changeset(attrs)
    |> Repo.insert()
  end

  # Update operations
  def update_user(user, attrs) do
    user
    |> User.changeset(attrs)
    |> Repo.update()
  end

  # Delete operations
  def delete_user(user), do: Repo.delete(user)
end
```

### Embedded Schemas

#### When to Use
- For JSON fields or complex data structures
- For data that doesn't need its own table
- For value objects

```elixir
defmodule MyApp.Accounts.Address do
  use Ecto.Schema
  import Ecto.Changeset

  @primary_key false
  embedded_schema do
    field :street, :string
    field :city, :string
    field :state, :string
    field :zip, :string
  end

  def changeset(address, attrs) do
    address
    |> cast(attrs, [:street, :city, :state, :zip])
    |> validate_required([:city, :state])
  end
end

defmodule MyApp.Accounts.User do
  use Ecto.Schema

  schema "users" do
    field :name, :string
    embeds_one :address, MyApp.Accounts.Address
    timestamps()
  end
end
```

## Phoenix Best Practices

### Context Design

#### Bounded Contexts
```elixir
# Good - Clear context boundaries
defmodule MyApp.Accounts do
  # User management
end

defmodule MyApp.Content do
  # Posts, comments
end

defmodule MyApp.Billing do
  # Subscriptions, invoices
end
```

#### Context Principles
- **Domain-driven**: Organize by business domain, not technical concerns
- **Single responsibility**: Each context handles one area of the domain
- **Explicit APIs**: Public functions form the context's contract
- **No cross-context queries**: Contexts interact through public APIs

### Controller Patterns

#### Thin Controllers
```elixir
defmodule MyAppWeb.UserController do
  use MyAppWeb, :controller
  alias MyApp.Accounts

  def index(conn, params) do
    users = Accounts.list_users(params)
    render(conn, :index, users: users)
  end

  def create(conn, %{"user" => user_params}) do
    case Accounts.create_user(user_params) do
      {:ok, user} ->
        conn
        |> put_flash(:info, "User created successfully.")
        |> redirect(to: ~p"/users/#{user}")

      {:error, %Ecto.Changeset{} = changeset} ->
        render(conn, :new, changeset: changeset)
    end
  end
end
```

#### Controller Best Practices
- **Keep thin**: Controllers should only handle HTTP concerns
- **Delegate to contexts**: Business logic belongs in contexts
- **Pattern match params**: Validate parameter structure early
- **Error handling**: Handle both success and error cases explicitly

### LiveView Patterns

#### LiveView Structure
```elixir
defmodule MyAppWeb.UserLive.Index do
  use MyAppWeb, :live_view
  alias MyApp.Accounts

  def mount(_params, _session, socket) do
    {:ok, assign(socket, users: Accounts.list_users())}
  end

  def handle_params(params, _uri, socket) do
    {:noreply, apply_action(socket, socket.assigns.live_action, params)}
  end

  defp apply_action(socket, :index, _params) do
    assign(socket, :page_title, "Users")
  end

  defp apply_action(socket, :new, _params) do
    assign(socket, :page_title, "New User")
    assign(socket, :user, %User{})
  end

  def handle_event("delete", %{"id" => id}, socket) do
    user = Accounts.get_user!(id)
    {:ok, _} = Accounts.delete_user(user)
    {:noreply, assign(socket, users: Accounts.list_users())}
  end
end
```

#### LiveView Best Practices
- **Assign organization**: Keep assigns flat and organized
- **Event naming**: Use consistent, descriptive event names
- **Handle info**: Implement `handle_info/2` for background updates
- **Temporary assigns**: Use for large lists that don't need to persist
- **Streams**: Use for efficient list updates

#### Streams for Efficiency
```elixir
def mount(_params, _session, socket) do
  socket =
    socket
    |> stream(:users, Accounts.list_users())

  {:ok, socket}
end

def handle_event("add_user", %{"user" => attrs}, socket) do
  {:ok, user} = Accounts.create_user(attrs)
  {:noreply, stream_insert(socket, :users, user, at: 0)}
end
```

### Authentication & Authorization

#### Modern Auth with mix phx.gen.auth
```elixir
# Use the generated authentication system
mix phx.gen.auth Accounts User users

# Then customize as needed
defmodule MyAppWeb.UserAuth do
  # Generated plugs and functions
  # Customize behavior here
end
```

#### Authorization Patterns
```elixir
# Policy modules
defmodule MyApp.Accounts.Policy do
  def can_edit?(%User{id: user_id}, %Post{user_id: post_user_id}) do
    user_id == post_user_id
  end

  def can_edit?(%User{role: :admin}, %Post{}), do: true
  def can_edit?(_, _), do: false
end

# In controllers
def edit(conn, %{"id" => id}) do
  post = Content.get_post!(id)

  if Accounts.Policy.can_edit?(conn.assigns.current_user, post) do
    render(conn, :edit, post: post)
  else
    conn
    |> put_flash(:error, "Unauthorized")
    |> redirect(to: ~p"/")
  end
end
```

### Testing Patterns

#### Context Testing
```elixir
defmodule MyApp.AccountsTest do
  use MyApp.DataCase
  alias MyApp.Accounts

  describe "users" do
    test "list_users/0 returns all users" do
      user = insert(:user)
      assert Accounts.list_users() == [user]
    end

    test "create_user/1 with valid data creates a user" do
      attrs = %{email: "test@example.com", name: "Test"}
      assert {:ok, %User{} = user} = Accounts.create_user(attrs)
      assert user.email == "test@example.com"
    end

    test "create_user/1 with invalid data returns error changeset" do
      assert {:error, %Ecto.Changeset{}} = Accounts.create_user(%{})
    end
  end
end
```

#### Controller Testing
```elixir
defmodule MyAppWeb.UserControllerTest do
  use MyAppWeb.ConnCase

  describe "index" do
    test "lists all users", %{conn: conn} do
      conn = get(conn, ~p"/users")
      assert html_response(conn, 200) =~ "Users"
    end
  end

  describe "create user" do
    test "redirects to show when data is valid", %{conn: conn} do
      attrs = %{email: "test@example.com", name: "Test"}
      conn = post(conn, ~p"/users", user: attrs)

      assert %{id: id} = redirected_params(conn)
      assert redirected_to(conn) == ~p"/users/#{id}"
    end
  end
end
```

#### LiveView Testing
```elixir
defmodule MyAppWeb.UserLive.IndexTest do
  use MyAppWeb.ConnCase
  import Phoenix.LiveViewTest

  test "displays users", %{conn: conn} do
    user = insert(:user)
    {:ok, _view, html} = live(conn, ~p"/users")
    assert html =~ user.name
  end

  test "creates new user", %{conn: conn} do
    {:ok, view, _html} = live(conn, ~p"/users")

    assert view
           |> form("#user-form", user: %{name: "Test", email: "test@example.com"})
           |> render_submit()

    assert_patch(view, ~p"/users")
  end
end
```

## Common Anti-Patterns to Avoid

### Ecto Anti-Patterns
1. **N+1 queries**: Always preload associations
2. **Large changesets**: Split into operation-specific changesets
3. **Business logic in migrations**: Keep migrations simple
4. **String types for enums**: Use `Ecto.Enum`
5. **Skipping constraints**: Always add database constraints
6. **Ignoring transactions**: Use transactions for multi-step operations
7. **Dynamic atoms**: Never use `String.to_atom/1` with user input

### Phoenix Anti-Patterns
1. **Fat controllers**: Move logic to contexts
2. **Context bypassing**: Always go through context APIs
3. **Direct Repo calls in controllers**: Use contexts
4. **No error handling**: Always handle {:ok, _} and {:error, _}
5. **Global assigns**: Minimize assigns in layouts
6. **Inline HTML in controllers**: Use templates and views
7. **Shared database connections**: Each test should be isolated

### LiveView Anti-Patterns
1. **Large assigns**: Don't assign entire datasets; use streams
2. **Polling**: Use PubSub instead of periodic polling
3. **No loading states**: Always show loading indicators
4. **Blocking operations**: Use async tasks for slow operations
5. **Ignoring handle_info**: Always implement for background updates
