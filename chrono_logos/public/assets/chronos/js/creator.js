(() => {
  const editor = document.getElementById("creator-editor");

  if (!editor) {
    return;
  }

  const gameId = editor.dataset.gameId;

  const urls = {
    saveGame: editor.dataset.saveGame,

    addCard: editor.dataset.addCard,

    saveCard: editor.dataset.saveCard,

    deleteCard: editor.dataset.deleteCard,

    uploadImage: editor.dataset.uploadCardImage,

    deleteImage: editor.dataset.deleteCardImage,

    reorder: editor.dataset.reorderCards,
  };
  const csrf = document.getElementById("creator-csrf");
  const saveStatus = document.getElementById("save-status");

  const cardsBody = document.getElementById("cards-body");
  const board = document.getElementById("cards-board");

  const tableView = document.getElementById("table-view");
  const boardView = document.getElementById("board-view");

  const viewButtons = document.querySelectorAll(".creator-view-btn");

  const viewStorageKey = `creator-view-${gameId}`;
  function getCurrentCardOrder() {
    return [...cardsBody.querySelectorAll(".card-row")].map((row) =>
      Number(row.dataset.cardId),
    );
  }
  async function saveCardOrder() {
    try {
      await post(urls.reorder, {
        game_id: gameId,

        order: JSON.stringify(getCurrentCardOrder()),
      });

      markSaved();
    } catch (error) {
      console.error(error);

      setStatus("● Ошибка сохранения", "error");

      showAlert("danger", error.message);
    }
  }
  let draggedRow = null;

  /*
   * Разрешаем drag только
   * после нажатия на ручку.
   */
  cardsBody.addEventListener("mousedown", (event) => {
    const handle = event.target.closest(".drag-handle");

    if (!handle) {
      return;
    }

    const row = handle.closest(".card-row");

    row.draggable = true;
  });

  cardsBody.addEventListener("dragstart", (event) => {
    const row = event.target.closest(".card-row");

    if (!row) {
      return;
    }

    draggedRow = row;

    row.classList.add("dragging");

    event.dataTransfer.effectAllowed = "move";
  });

  cardsBody.addEventListener("dragover", (event) => {
    if (!draggedRow) {
      return;
    }

    event.preventDefault();

    const rows = [...cardsBody.querySelectorAll(".card-row:not(.dragging)")];

    let nextRow = null;

    for (const row of rows) {
      const box = row.getBoundingClientRect();

      if (event.clientY < box.top + box.height / 2) {
        nextRow = row;

        break;
      }
    }

    if (nextRow) {
      cardsBody.insertBefore(draggedRow, nextRow);
    } else {
      cardsBody.appendChild(draggedRow);
    }
  });

  cardsBody.addEventListener("dragend", async (event) => {
    const row = event.target.closest(".card-row");

    if (!row) {
      return;
    }

    row.classList.remove("dragging");

    row.draggable = false;

    draggedRow = null;

    renumberCards();

    renderBoard();

    await saveCardOrder();
  });

  function createElement(tag, className, text = "") {
    const element = document.createElement(tag);

    element.className = className;

    element.textContent = text;

    return element;
  }
  function getRowField(row, field) {
    const input = row.querySelector(`[data-field="${field}"]`);

    return input ? input.value : "";
  }
  function renderBoard() {
    refreshSelection();
    board.innerHTML = "";

    const rows = [...cardsBody.querySelectorAll(".card-row")];

    rows.forEach((row, index) => {
      const card = document.createElement("article");

      card.className = "board-card";
      const included = row.querySelector('.card-included')?.checked !== false;
      card.classList.toggle('card-excluded', !included);
      card.appendChild(createElement('small', 'card-membership', included ? 'В игре' : 'Выключена'));

      card.hidden = row.hidden;
      card.draggable = true;

      card.dataset.cardId = row.dataset.cardId;

      /*
       * NUMBER
       */
      card.appendChild(
        createElement("div", "board-card-number", `#${index + 1}`),
      );

      /*
       * CATEGORY
       */
      card.appendChild(
        createElement(
          "div",
          "board-card-category",

          getRowField(row, "category") || "БЕЗ КАТЕГОРИИ",
        ),
      );
      const imageSrc = row.dataset.imageSrc;

      if (imageSrc) {
        const image = document.createElement("img");

        image.className = "board-card-image";

        image.src = imageSrc;

        image.alt = getRowField(row, "title");

        card.appendChild(image);
      }

      /*
       * TITLE
       */
      card.appendChild(
        createElement(
          "div",
          "board-card-title",

          getRowField(row, "title") || "Без названия",
        ),
      );

      /*
       * DESCRIPTION
       */
      card.appendChild(
        createElement(
          "div",
          "board-card-description",

          getRowField(row, "short_description") || "Описание отсутствует",
        ),
      );

      /*
       * FOOTER
       */
      const footer = document.createElement("div");

      footer.className = "board-card-footer";

      const chronology = document.createElement("div");

      chronology.appendChild(
        createElement(
          "div",
          "board-sort-order",

          getRowField(row, "sort_order") || "—",
        ),
      );

      chronology.appendChild(
        createElement(
          "div",
          "board-revealed",

          getRowField(row, "revealed_value") || "",
        ),
      );

      footer.appendChild(chronology);

      footer.appendChild(
        createElement(
          "div",
          "board-difficulty",

          getRowField(row, "difficulty") || "NORMAL",
        ),
      );

      card.appendChild(footer);

      board.appendChild(card);
    });
  }
  function setCreatorView(view) {
    const isBoard = view === "board";

    tableView.classList.toggle("is-hidden", isBoard);

    boardView.classList.toggle("is-hidden", !isBoard);

    viewButtons.forEach((button) => {
      button.classList.toggle("active", button.dataset.view === view);
    });

    if (isBoard) {
      renderBoard();
    }

    localStorage.setItem(viewStorageKey, view);
  }

  viewButtons.forEach((button) => {
    button.addEventListener("click", () => {
      setCreatorView(button.dataset.view);
    });
  });

  setCreatorView(localStorage.getItem(viewStorageKey) ?? "table");
  let draggedBoardCard = null;

  board.addEventListener("dragstart", (event) => {
    const card = event.target.closest(".board-card");

    if (!card) {
      return;
    }

    draggedBoardCard = card;

    card.classList.add("dragging");

    event.dataTransfer.effectAllowed = "move";
  });
  board.addEventListener("dragover", (event) => {
    if (!draggedBoardCard) {
      return;
    }

    event.preventDefault();

    const target = event.target.closest(".board-card:not(.dragging)");

    if (!target) {
      return;
    }

    const rect = target.getBoundingClientRect();

    const middleX = rect.left + rect.width / 2;

    const middleY = rect.top + rect.height / 2;

    let insertBefore = false;

    /*
     * Если карточки примерно
     * находятся на одной строке —
     * ориентируемся по X.
     */
    if (event.clientY >= rect.top && event.clientY <= rect.bottom) {
      insertBefore = event.clientX < middleX;
    } else {
      insertBefore = event.clientY < middleY;
    }

    board.insertBefore(
      draggedBoardCard,
      insertBefore ? target : target.nextSibling,
    );
  });
  board.addEventListener("dragend", async (event) => {
    const card = event.target.closest(".board-card");

    if (!card) {
      return;
    }

    card.classList.remove("dragging");

    draggedBoardCard = null;

    /*
     * Получаем новый порядок
     * со стола.
     */
    const order = [...board.querySelectorAll(".board-card")].map(
      (card) => card.dataset.cardId,
    );

    /*
     * Переставляем строки таблицы
     * в том же порядке.
     */
    order.forEach((cardId) => {
      const row = cardsBody.querySelector(`[data-card-id="${cardId}"]`);

      if (row) {
        cardsBody.appendChild(row);
      }
    });

    renumberCards();

    renderBoard();

    await saveCardOrder();
  });

  /*
   * Очередь AJAX.
   *
   * Не отправляем несколько POST одновременно,
   * чтобы CSRF token обновлялся последовательно.
   */
  let requestQueue = Promise.resolve();

  const timers = new Map();

  /*
   * localStorage только как страховка.
   *
   * Основные данные всегда находятся
   * в PostgreSQL.
   */
  const pendingKey = `creator-pending-${gameId}`;

  function getPending() {
    try {
      return (
        JSON.parse(localStorage.getItem(pendingKey)) ?? {
          game: null,
          cards: {},
        }
      );
    } catch {
      return {
        game: null,
        cards: {},
      };
    }
  }

  function writePending(data) {
    localStorage.setItem(pendingKey, JSON.stringify(data));
  }

  function setStatus(text, type) {
    saveStatus.textContent = text;

    saveStatus.className = `save-status ${type}`;
  }

  function updateCsrf(data) {
    if (data.csrfName && data.csrfHash) {
      csrf.name = data.csrfName;
      csrf.value = data.csrfHash;
    }
  }

  async function rawPost(url, data) {
    setStatus("● Сохраняем…", "saving");

    const formData = new FormData();

    Object.entries(data).forEach(([key, value]) => {
      formData.append(key, value ?? "");
    });

    formData.append(csrf.name, csrf.value);

    const response = await fetch(url, {
      method: "POST",

      body: formData,

      headers: {
        "X-Requested-With": "XMLHttpRequest",
      },
    });

    let result;

    try {
      result = await response.json();
    } catch {
      throw new Error("Сервер вернул некорректный ответ.");
    }

    updateCsrf(result);

    if (result.redirect) {
      window.location.href = result.redirect;

      throw new Error("Session expired");
    }

    if (!response.ok || result.success === false) {
      throw new Error(result.message ?? "Ошибка сохранения");
    }

    return result;
  }

  /*
   * Все POST идут строго друг за другом.
   */
  function post(url, data) {
    requestQueue = requestQueue.catch(() => {}).then(() => rawPost(url, data));

    return requestQueue;
  }

  function markSaved() {
    const time = new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });

    setStatus(`● Сохранено ${time}`, "saved");
  }

  function schedule(key, callback) {
    if (timers.has(key)) {
      clearTimeout(timers.get(key));
    }

    const timer = setTimeout(() => {
      timers.delete(key);

      callback();
    }, 600);

    timers.set(key, timer);
  }

  /*
   * GAME AUTOSAVE
   */

  const titleInput = document.getElementById("game-title");

  const descriptionInput = document.getElementById("game-description");

  function rememberGame() {
    const pending = getPending();

    pending.game = {
      title: titleInput.value,
      description: descriptionInput.value,
    };

    writePending(pending);

    setStatus("● Есть изменения", "saving");
  }

  async function saveGame() {
    try {
      await post(urls.saveGame, {
        game_id: gameId,

        title: titleInput.value,

        description: descriptionInput.value,
      });

      const pending = getPending();

      pending.game = null;

      writePending(pending);

      markSaved();
    } catch (error) {
      console.error(error);

      setStatus("● Ошибка сохранения", "error");

      showAlert("danger", error.message);
    }
  }

  [titleInput, descriptionInput].forEach((input) => {
    input.addEventListener("input", () => {
      rememberGame();

      schedule("game", saveGame);
    });
  });

  /*
   * CARD SERIALIZATION
   */

  function getCardData(row) {
    const data = {
      card_id: row.dataset.cardId,
    };

    row.querySelectorAll("[data-field]").forEach((input) => {
      data[input.dataset.field] = input.value;
    });

    return data;
  }

  function rememberCard(row) {
    const pending = getPending();

    pending.cards ??= {};

    pending.cards[row.dataset.cardId] = getCardData(row);

    writePending(pending);

    setStatus("● Есть изменения", "saving");
  }

  async function saveCard(row) {
    const cardId = row.dataset.cardId;

    try {
      await post(urls.saveCard, getCardData(row));

      const pending = getPending();

      if (pending.cards) {
        delete pending.cards[cardId];
      }

      writePending(pending);

      markSaved();
    } catch (error) {
      console.error(error);

      setStatus("● Ошибка сохранения", "error");

      showAlert("danger", error.message);
    }
  }

  /*
   * Event delegation.
   *
   * Работает и для новых строк,
   * добавленных после загрузки страницы.
   */
  cardsBody.addEventListener("input", (event) => {
    const field = event.target.closest("[data-field]");

    if (!field) {
      return;
    }

    const row = field.closest(".card-row");

    rememberCard(row);

    schedule(`card-${row.dataset.cardId}`, () => saveCard(row));
  });

  cardsBody.addEventListener("change", (event) => {
    const field = event.target.closest("[data-field]");

    if (!field) {
      return;
    }

    const row = field.closest(".card-row");

    rememberCard(row);

    schedule(`card-${row.dataset.cardId}`, () => saveCard(row));
  });

  /*
   * ADD CARD
   */

  function buildCardRow(card) {
    const row = document.createElement("tr");

    row.className = "card-row";

    row.dataset.cardId = card.id;
    row.dataset.imageUrl = "";
    row.dataset.imageSrc = "";

    row.innerHTML = `

        <td class="drag-cell">

            <button
                type="button"
                class="drag-handle"
                title="Перетащить"
            >
                ⋮⋮
            </button>

        </td>


        <td class="row-number"></td>


        <td>

            <input
                data-field="title"
                type="text"
                placeholder="Название события"
            >

        </td>


        <td>

            <input
                data-field="short_description"
                type="text"
                placeholder="Краткое описание"
            >

        </td>

        <td class="card-image-cell">

    <div
        class="card-image-dropzone"
        title="Нажмите или перетащите изображение"
    >

        <div class="card-image-preview">

            <img
                class="card-image-thumb"
                src=""
                alt=""
                hidden
            >

            <span class="card-image-empty">
                <strong>＋</strong>
                <span>Добавить фото</span>
                <small>или перетащите</small>
            </span>

            <div
                class="card-image-loading"
                hidden
            >
                Загрузка…
            </div>

        </div>

    </div>


    <input
        type="file"
        class="card-image-input"
        accept="image/jpeg,image/png,image/webp"
        hidden
    >


    <div class="card-image-actions">

        <button
            type="button"
            class="card-image-button"
        >
            Выбрать
        </button>

        <button
            type="button"
            class="card-image-delete-button"
            title="Удалить изображение"
            hidden
        >
            ×
        </button>

    </div>

</td>
        <td>

            <input
                                    data-field="sort_order"
                                    class="sort-order-input"
                                    type="text"
                                    inputmode="decimal"
                                    value="<?= esc($card['sort_order'] ?? '') ?>"
                                    placeholder="Порядок">

        </td>


        <td>

            <input
        data-field="revealed_value"
        type="text"
        value="<?= esc($card['revealed_value'] ?? '') ?>"
        placeholder="Что показать после ответа">
            </td>


        <td>

            <input
                data-field="category"
                type="text"
                placeholder="Космос"
            >

        </td>


        <td>

            <select data-field="difficulty">

                <option value="EASY">
                    EASY
                </option>

                <option
                    value="NORMAL"
                    selected
                >
                    NORMAL
                </option>

                <option value="HARD">
                    HARD
                </option>

                <option value="EXPERT">
                    EXPERT
                </option>

            </select>

        </td>


        <td>

            <button
                type="button"
                class="delete-card-btn"
                title="Удалить"
            >
                ×
            </button>

        </td>
    `;

    const included = document.createElement('td');
    included.innerHTML = '<input type="checkbox" class="card-included" aria-label="Включить карточку в игру" checked>';
    row.querySelector('.row-number').after(included);
    return row;
  }

  function renumberCards() {
    cardsBody.querySelectorAll(".card-row").forEach((row, index) => {
      row.querySelector(".row-number").textContent = index + 1;
    });
  }

  async function addCard() {
    try {
      const result = await post(urls.addCard, {
        game_id: gameId,
      });

      const row = buildCardRow(result.card);

      cardsBody.appendChild(row);

      renumberCards();

      renderBoard();

      markSaved();
      row.querySelector('[data-field="title"]').focus();
    } catch (error) {
      showAlert("danger", error.message);
    }
  }

  document.getElementById("add-card").addEventListener("click", addCard);
  const addCardBottom = document.getElementById("add-card-bottom");

  if (addCardBottom) {
    addCardBottom.addEventListener("click", addCard);
  }

  /*
   * DELETE CARD
   */
  /*
   * CARD IMAGE
   */

  const allowedImageTypes = ["image/jpeg", "image/png", "image/webp"];

  const maxImageSize = 5 * 1024 * 1024;

  /*
   * Обновляет визуальное состояние
   * изображения одной строки.
   */
  function updateCardImageUi(row, imageUrl = "", imageSrc = "") {
    row.dataset.imageUrl = imageUrl || "";

    row.dataset.imageSrc = imageSrc || "";

    const image = row.querySelector(".card-image-thumb");

    const empty = row.querySelector(".card-image-empty");

    const selectButton = row.querySelector(".card-image-button");

    const deleteButton = row.querySelector(".card-image-delete-button");

    if (imageSrc) {
      image.src = imageSrc;

      image.hidden = false;

      empty.hidden = true;

      selectButton.textContent = "Заменить";

      deleteButton.hidden = false;
    } else {
      image.removeAttribute("src");

      image.hidden = true;

      empty.hidden = false;

      selectButton.textContent = "Выбрать";

      deleteButton.hidden = true;
    }
  }

  /*
   * Простая проверка на клиенте.
   *
   * Это только UX.
   * Настоящая проверка находится
   * в Creator.php.
   */
  function validateCardImage(file) {
    if (!allowedImageTypes.includes(file.type)) {
      showAlert("warning", "Разрешены только JPG, PNG и WebP.");

      return false;
    }

    if (file.size > maxImageSize) {
      showAlert("warning", "Размер изображения не должен превышать 5 MB.");

      return false;
    }

    return true;
  }

  /*
   * Загрузка / замена изображения.
   */
  async function uploadCardImage(row, file) {
    if (!row || !file) {
      return;
    }

    if (!validateCardImage(file)) {
      return;
    }

    const button = row.querySelector(".card-image-button");

    const deleteButton = row.querySelector(".card-image-delete-button");

    const dropzone = row.querySelector(".card-image-dropzone");

    const loading = row.querySelector(".card-image-loading");

    const image = row.querySelector(".card-image-thumb");

    const empty = row.querySelector(".card-image-empty");

    /*
     * Сохраняем старое состояние.
     * Если сервер отклонит файл —
     * вернём его.
     */
    const oldImageUrl = row.dataset.imageUrl || "";

    const oldImageSrc = row.dataset.imageSrc || "";

    /*
     * Мгновенный локальный preview.
     */
    const previewUrl = URL.createObjectURL(file);

    image.src = previewUrl;

    image.hidden = false;

    empty.hidden = true;

    button.disabled = true;

    deleteButton.disabled = true;

    dropzone.classList.add("is-uploading");

    loading.hidden = false;

    try {
      const result = await post(urls.uploadImage, {
        card_id: row.dataset.cardId,

        image: file,
      });

      /*
       * Уже серверный постоянный URL.
       */
      updateCardImageUi(row, result.image_url, result.image_src);

      renderBoard();

      markSaved();

      showAlert("success", result.message ?? "Изображение сохранено.");
    } catch (error) {
      console.error(error);

      /*
       * Upload не удался —
       * возвращаем предыдущее состояние.
       */
      updateCardImageUi(row, oldImageUrl, oldImageSrc);

      renderBoard();

      showAlert("danger", error.message);
    } finally {
      URL.revokeObjectURL(previewUrl);

      button.disabled = false;

      deleteButton.disabled = false;

      dropzone.classList.remove("is-uploading");

      loading.hidden = true;
    }
  }

  /*
   * Нажатие на кнопку Выбрать / Заменить.
   */
  cardsBody.addEventListener("click", (event) => {
    const button = event.target.closest(".card-image-button");

    if (!button) {
      return;
    }

    const row = button.closest(".card-row");

    const input = row.querySelector(".card-image-input");

    input.click();
  });

  /*
   * Нажатие непосредственно
   * по области изображения.
   */
  cardsBody.addEventListener("click", (event) => {
    const dropzone = event.target.closest(".card-image-dropzone");

    if (!dropzone) {
      return;
    }

    const row = dropzone.closest(".card-row");

    const input = row.querySelector(".card-image-input");

    input.click();
  });

  /*
   * Выбор через системный диалог.
   */
  cardsBody.addEventListener("change", async (event) => {
    const input = event.target.closest(".card-image-input");

    if (!input) {
      return;
    }

    const file = input.files?.[0];

    if (!file) {
      return;
    }

    const row = input.closest(".card-row");

    await uploadCardImage(row, file);

    /*
     * Позволяет выбрать тот же файл повторно.
     */
    input.value = "";
  });

  /*
   * Drag & Drop файла.
   */
  cardsBody.addEventListener("dragenter", (event) => {
    const dropzone = event.target.closest(".card-image-dropzone");

    if (!dropzone) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    dropzone.classList.add("is-dragover");
  });

  cardsBody.addEventListener("dragover", (event) => {
    const dropzone = event.target.closest(".card-image-dropzone");

    if (!dropzone) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = "copy";
    }

    dropzone.classList.add("is-dragover");
  });

  cardsBody.addEventListener("dragleave", (event) => {
    const dropzone = event.target.closest(".card-image-dropzone");

    if (!dropzone) {
      return;
    }

    event.stopPropagation();

    dropzone.classList.remove("is-dragover");
  });

  cardsBody.addEventListener("drop", async (event) => {
    const dropzone = event.target.closest(".card-image-dropzone");

    if (!dropzone) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    dropzone.classList.remove("is-dragover");

    const file = event.dataTransfer?.files?.[0];

    if (!file) {
      return;
    }

    const row = dropzone.closest(".card-row");

    await uploadCardImage(row, file);
  });

  /*
   * Удаление только изображения.
   */
  cardsBody.addEventListener("click", async (event) => {
    const button = event.target.closest(".card-image-delete-button");

    if (!button) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    const row = button.closest(".card-row");

    if (!confirm("Удалить изображение этой карточки?")) {
      return;
    }

    button.disabled = true;

    try {
      const result = await post(urls.deleteImage, {
        card_id: row.dataset.cardId,
      });

      updateCardImageUi(row, "", "");

      renderBoard();

      markSaved();

      showAlert("success", result.message ?? "Изображение удалено.");
    } catch (error) {
      console.error(error);

      showAlert("danger", error.message);
    } finally {
      button.disabled = false;
    }
  });
  /*
   * DELETE CARD
   */

  cardsBody.addEventListener("click", async (event) => {
    const button = event.target.closest(".delete-card-btn");

    if (!button) {
      return;
    }

    const row = button.closest(".card-row");

    if (!confirm("Удалить эту карточку?")) {
      return;
    }

    button.disabled = true;

    try {
      await post(urls.deleteCard, {
        card_id: row.dataset.cardId,
      });

      const pending = getPending();

      if (pending.cards) {
        delete pending.cards[row.dataset.cardId];
      }

      writePending(pending);

      row.remove();

      renumberCards();

      renderBoard();

      /*
       * После удаления карточки
       * сохраняем новый editor_position
       * оставшихся карточек.
       */
      await saveCardOrder();

      markSaved();

      showAlert("success", "Карточка удалена.");
    } catch (error) {
      console.error(error);

      button.disabled = false;

      showAlert("danger", error.message);
    }
  });

  /*
   * RESTORE AFTER REFRESH
   */

  function restorePending() {
    const pending = getPending();

    let restored = false;

    if (pending.game) {
      titleInput.value = pending.game.title ?? "";

      descriptionInput.value = pending.game.description ?? "";

      restored = true;

      schedule("restore-game", saveGame);
    }

    if (pending.cards) {
      Object.entries(pending.cards).forEach(([cardId, values]) => {
        const row = cardsBody.querySelector(`[data-card-id="${cardId}"]`);

        if (!row) {
          return;
        }

        Object.entries(values).forEach(([field, value]) => {
          if (field === "card_id") {
            return;
          }

          const input = row.querySelector(`[data-field="${field}"]`);

          if (input) {
            input.value = value ?? "";
          }
        });

        restored = true;

        schedule(`restore-card-${cardId}`, () => saveCard(row));
      });
    }

    if (restored) {
      renderBoard();

      showAlert("info", "Восстановлены несохранённые изменения.");
    }
  }

  /*
   * Ctrl + Enter
   */
  document.addEventListener("keydown", (event) => {
    if (event.ctrlKey && event.key === "Enter") {
      event.preventDefault();

      addCard();
    }
  });


  function selectionRows() { return [...cardsBody.querySelectorAll('.card-row')]; }
  function refreshSelection() {
    const category = document.getElementById('card-category');
    if (!category) return;
    const selected = category.value;
    const categories = [...new Set(selectionRows().map(row => getRowField(row, 'category')).filter(Boolean))].sort();
    category.replaceChildren(new Option('Все разделы', ''), ...categories.map(value => new Option(value, value)));
    category.value = categories.includes(selected) ? selected : '';
    const query = document.getElementById('card-search').value.trim().toLocaleLowerCase();
    const state = document.getElementById('card-state').value;
    const rows = selectionRows();
    rows.forEach(row => {
      const included = row.querySelector('.card-included')?.checked !== false;
      row.classList.toggle('card-excluded', !included);
      row.hidden = (category.value && getRowField(row, 'category') !== category.value)
        || (state === 'on' && !included) || (state === 'off' && included)
        || ![getRowField(row,'title'),getRowField(row,'short_description'),getRowField(row,'category')].join(' ').toLocaleLowerCase().includes(query);
    });
    document.getElementById('selection-summary').textContent = `В игре: ${rows.filter(r => r.querySelector('.card-included')?.checked !== false).length} из ${rows.length} · показано: ${rows.filter(r => !r.hidden).length}`;
  }
  async function changeSelection(rows, enabled) {
    if (!rows.length) return;
    try {
      await post('/creator/select-cards', {game_id:gameId, ids:JSON.stringify(rows.map(r => Number(r.dataset.cardId))), enabled:enabled?'1':'0'});
      rows.forEach(row => row.querySelector('.card-included').checked = enabled);
      markSaved();
      return true;
    } catch (error) { showAlert('danger', error.message); return false; }
    finally { renderBoard(); }
  }
  cardsBody.addEventListener('change', async event => {
    const checkbox = event.target.closest('.card-included');
    if (!checkbox) return;
    const enabled = checkbox.checked;
    checkbox.disabled = true;
    const saved = await changeSelection([checkbox.closest('.card-row')], enabled);
    if (!saved) { checkbox.checked = !enabled; renderBoard(); }
    checkbox.disabled = false;
  });
  for (const id of ['card-search','card-category','card-state']) document.getElementById(id).addEventListener('input', renderBoard);
  for (const [id, enabled] of [['include-visible',true],['exclude-visible',false]]) {
    document.getElementById(id).onclick = async event => {
      const button = event.currentTarget;
      button.disabled = true;
      await changeSelection(selectionRows().filter(row => !row.hidden), enabled);
      button.disabled = false;
    };
  }
  refreshSelection();
  cardsBody.addEventListener('input', event => { if (event.target.closest('[data-field]')) renderBoard(); });
  restorePending();
})();


/*
 * Горизонтальная прокрутка таблицы карточек.
 *
 * Таблица шире контейнера, но раньше об этом ничего не сообщало: подсказок у
 * краёв не было, а обычное колесо мыши даёт только deltaY и потому таблицу не
 * двигало вовсе.
 */
(() => {
  const wrap = document.getElementById("creator-table-wrap");

  if (!wrap) {
    return;
  }

  const scroller = wrap.closest(".creator-table-scroller");
  const fadeLeft = scroller?.querySelector(".table-scroll-fade-left");
  const fadeRight = scroller?.querySelector(".table-scroll-fade-right");

  const update = () => {
    const max = wrap.scrollWidth - wrap.clientWidth;
    const x = wrap.scrollLeft;

    fadeLeft?.classList.toggle("is-visible", x > 4);
    fadeRight?.classList.toggle("is-visible", max > 4 && x < max - 4);
  };

  wrap.addEventListener("scroll", update, { passive: true });
  window.addEventListener("resize", update);

  wrap.addEventListener(
    "wheel",
    event => {
      /* Ctrl+колесо — это зум браузера, не трогаем. */
      if (event.ctrlKey) {
        return;
      }

      const max = wrap.scrollWidth - wrap.clientWidth;

      if (max <= 0) {
        return;
      }

      /* Трекпад уже сообщает горизонталь сам. */
      if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) {
        return;
      }

      const atStart = wrap.scrollLeft <= 0;
      const atEnd = wrap.scrollLeft >= max - 1;

      /*
       * У края событие отдаём странице — иначе колесо запирается в таблице
       * и страница перестаёт прокручиваться.
       */
      if ((event.deltaY < 0 && atStart) || (event.deltaY > 0 && atEnd)) {
        return;
      }

      event.preventDefault();
      wrap.scrollLeft += event.deltaY;
    },
    { passive: false }
  );

  /* Вид «Таблица» может быть скрыт на момент загрузки. */
  if (typeof ResizeObserver === "function") {
    new ResizeObserver(update).observe(wrap);
  }

  update();

})();
