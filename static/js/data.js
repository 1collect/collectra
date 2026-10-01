/* Browser-local demo repository. No API, credentials or authentication. */
(function (A) {
  'use strict';
  const seed = {
  "users": [
    {
      "id": 1001,
      "name": "\u0410\u0440\u0448\u0438\u0434\u0438\u043d \u041a.",
      "email": "arshidin.k@example.com",
      "department": "IT",
      "role": "Developer",
      "status": "active",
      "created": "2026-09-30",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1002,
      "name": "\u0418\u0432\u0430\u043d \u0418\u0432\u0430\u043d\u043e\u0432",
      "email": "ivan.ivanov@example.com",
      "department": "HR",
      "role": "Recruiter",
      "status": "pending",
      "created": "2026-09-29",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1003,
      "name": "\u0410\u043d\u043d\u0430 \u0421\u043c\u0438\u0440\u043d\u043e\u0432\u0430",
      "email": "anna.smirnova@example.com",
      "department": "Finance",
      "role": "Accountant",
      "status": "inactive",
      "created": "2026-09-28",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1004,
      "name": "Aigerim Sadykova",
      "email": "aigerim.s@example.com",
      "department": "Operations",
      "role": "Coordinator",
      "status": "active",
      "created": "2026-09-27",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1005,
      "name": "Daniyar Akhmetov",
      "email": "daniyar.a@example.com",
      "department": "Sales",
      "role": "Sales manager",
      "status": "active",
      "created": "2026-09-26",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1006,
      "name": "Elena Petrova",
      "email": "elena.p@example.com",
      "department": "Support",
      "role": "Support specialist",
      "status": "active",
      "created": "2026-09-25",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1007,
      "name": "Timur Beketov",
      "email": "timur.b@example.com",
      "department": "IT",
      "role": "Developer",
      "status": "active",
      "created": "2026-09-24",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1008,
      "name": "Sofia Volkova",
      "email": "sofia.v@example.com",
      "department": "HR",
      "role": "Recruiter",
      "status": "pending",
      "created": "2026-09-23",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1009,
      "name": "Asel Karimova",
      "email": "asel.k@example.com",
      "department": "Finance",
      "role": "Accountant",
      "status": "active",
      "created": "2026-09-22",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1010,
      "name": "Nikita Orlov",
      "email": "nikita.o@example.com",
      "department": "Operations",
      "role": "Coordinator",
      "status": "inactive",
      "created": "2026-09-21",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1011,
      "name": "Aliya Omarova",
      "email": "aliya.o@example.com",
      "department": "Sales",
      "role": "Sales manager",
      "status": "active",
      "created": "2026-09-20",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1012,
      "name": "Sergey Morozov",
      "email": "sergey.m@example.com",
      "department": "Support",
      "role": "Support specialist",
      "status": "blocked",
      "created": "2026-09-19",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1013,
      "name": "Diana Iskakova",
      "email": "diana.i@example.com",
      "department": "IT",
      "role": "Developer",
      "status": "active",
      "created": "2026-09-18",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1014,
      "name": "Maksim Sokolov",
      "email": "maksim.s@example.com",
      "department": "HR",
      "role": "Recruiter",
      "status": "active",
      "created": "2026-09-17",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1015,
      "name": "Madina Tulegen",
      "email": "madina.t@example.com",
      "department": "Finance",
      "role": "Accountant",
      "status": "pending",
      "created": "2026-09-16",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1016,
      "name": "Pavel Belov",
      "email": "pavel.b@example.com",
      "department": "Operations",
      "role": "Coordinator",
      "status": "active",
      "created": "2026-09-15",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1017,
      "name": "Amina Nurali",
      "email": "amina.n@example.com",
      "department": "Sales",
      "role": "Sales manager",
      "status": "active",
      "created": "2026-09-14",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1018,
      "name": "Viktor Lebedev",
      "email": "viktor.l@example.com",
      "department": "Support",
      "role": "Support specialist",
      "status": "active",
      "created": "2026-09-13",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1019,
      "name": "Kamila Nurgalieva",
      "email": "kamila.n@example.com",
      "department": "IT",
      "role": "Developer",
      "status": "inactive",
      "created": "2026-09-12",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1020,
      "name": "Arman Zhumabay",
      "email": "arman.z@example.com",
      "department": "HR",
      "role": "Recruiter",
      "status": "active",
      "created": "2026-09-11",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1021,
      "name": "Yulia Kuznetsova",
      "email": "yulia.k@example.com",
      "department": "Finance",
      "role": "Accountant",
      "status": "active",
      "created": "2026-09-10",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1022,
      "name": "Ruslan Mamedov",
      "email": "ruslan.m@example.com",
      "department": "Operations",
      "role": "Coordinator",
      "status": "pending",
      "created": "2026-09-09",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1023,
      "name": "Anastasia Frolova",
      "email": "anastasia.f@example.com",
      "department": "Sales",
      "role": "Sales manager",
      "status": "blocked",
      "created": "2026-09-08",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1024,
      "name": "Miras Alimov",
      "email": "miras.a@example.com",
      "department": "Support",
      "role": "Support specialist",
      "status": "active",
      "created": "2026-09-07",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1025,
      "name": "Vera Andreeva",
      "email": "vera.a@example.com",
      "department": "IT",
      "role": "Developer",
      "status": "active",
      "created": "2026-09-06",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1026,
      "name": "Dias Suleimen",
      "email": "dias.s@example.com",
      "department": "HR",
      "role": "Recruiter",
      "status": "active",
      "created": "2026-09-05",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1027,
      "name": "Polina Sorokina",
      "email": "polina.s@example.com",
      "department": "Finance",
      "role": "Accountant",
      "status": "active",
      "created": "2026-09-30",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1028,
      "name": "Azamat Ilyasov",
      "email": "azamat.i@example.com",
      "department": "Operations",
      "role": "Coordinator",
      "status": "inactive",
      "created": "2026-09-29",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1029,
      "name": "Irina Makarova",
      "email": "irina.m@example.com",
      "department": "Sales",
      "role": "Sales manager",
      "status": "pending",
      "created": "2026-09-28",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1030,
      "name": "Sanzhar Rakhim",
      "email": "sanzhar.r@example.com",
      "department": "Support",
      "role": "Support specialist",
      "status": "active",
      "created": "2026-09-27",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1031,
      "name": "Karina Ivanova",
      "email": "karina.i@example.com",
      "department": "IT",
      "role": "Developer",
      "status": "active",
      "created": "2026-09-26",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1032,
      "name": "Mikhail Kozlov",
      "email": "mikhail.k@example.com",
      "department": "HR",
      "role": "Recruiter",
      "status": "active",
      "created": "2026-09-25",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1033,
      "name": "Dana Saparova",
      "email": "dana.s@example.com",
      "department": "Finance",
      "role": "Accountant",
      "status": "active",
      "created": "2026-09-24",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1034,
      "name": "Nurlan Kenzhe",
      "email": "nurlan.k@example.com",
      "department": "Operations",
      "role": "Coordinator",
      "status": "blocked",
      "created": "2026-09-23",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1035,
      "name": "Olga Stepanova",
      "email": "olga.s@example.com",
      "department": "Sales",
      "role": "Sales manager",
      "status": "active",
      "created": "2026-09-22",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    },
    {
      "id": 1036,
      "name": "Alina Zaitseva",
      "email": "alina.z@example.com",
      "department": "Support",
      "role": "Support specialist",
      "status": "pending",
      "created": "2026-09-21",
      "phone": "",
      "comment": "Demo employee record. No real personal data."
    }
  ],
  "tasks": [
    {
      "id": 1,
      "title": "Review onboarding checklist",
      "assignee": "Aigerim Sadykova",
      "priority": "high",
      "due": "2026-09-30",
      "done": false
    },
    {
      "id": 2,
      "title": "Approve September access review",
      "assignee": "Daniyar Akhmetov",
      "priority": "medium",
      "due": "2026-09-30",
      "done": false
    },
    {
      "id": 3,
      "title": "Update department directory",
      "assignee": "Elena Petrova",
      "priority": "low",
      "due": "2026-10-01",
      "done": false
    },
    {
      "id": 4,
      "title": "Export monthly activity report",
      "assignee": "Anna Smirnova",
      "priority": "medium",
      "due": "2026-10-02",
      "done": false
    },
    {
      "id": 5,
      "title": "Publish internal UI guidelines",
      "assignee": "Timur Beketov",
      "priority": "low",
      "due": "2026-09-29",
      "done": true
    },
    {
      "id": 6,
      "title": "Prepare new employee accounts",
      "assignee": "Asel Karimova",
      "priority": "high",
      "due": "2026-10-02",
      "done": false
    }
  ],
  "logs": [
    {
      "id": 1,
      "time": "2026-09-30T10:42:00+05:00",
      "user": "Aigerim Sadykova",
      "action": "Created employee",
      "entity": "USR-1001",
      "ip": "192.0.2.12"
    },
    {
      "id": 2,
      "time": "2026-09-30T10:35:00+05:00",
      "user": "Daniyar Akhmetov",
      "action": "Updated access role",
      "entity": "Editor",
      "ip": "192.0.2.18"
    },
    {
      "id": 3,
      "time": "2026-09-30T10:28:00+05:00",
      "user": "Elena Petrova",
      "action": "Exported report",
      "entity": "September",
      "ip": "192.0.2.24"
    },
    {
      "id": 4,
      "time": "2026-09-30T10:14:00+05:00",
      "user": "Timur Beketov",
      "action": "Updated department",
      "entity": "Operations",
      "ip": "192.0.2.31"
    },
    {
      "id": 5,
      "time": "2026-09-30T09:52:00+05:00",
      "user": "Asel Karimova",
      "action": "Completed task",
      "entity": "TSK-0005",
      "ip": "192.0.2.42"
    }
  ]
};
  const clone = value => JSON.parse(JSON.stringify(value));
  const readList = (key, required) => {
    const value = A.storage.get(key, seed[key]);
    return Array.isArray(value) && value.every(item => item && required.every(field => field in item)) ? clone(value) : clone(seed[key]);
  };
  A.data = {
    departments: ['IT', 'HR', 'Finance', 'Operations', 'Sales', 'Support'],
    users: () => readList('users', ['id', 'name', 'email', 'department', 'status', 'created']),
    tasks: () => readList('tasks', ['id', 'title', 'done', 'priority']),
    logs: () => readList('logs', ['id', 'time', 'action', 'entity']),
    saveUsers(users, action = 'Updated employees', entity = 'Directory') {
      A.storage.set('users', users); this.log(action, entity); A.emit('demo:users-changed');
    },
    saveTasks(tasks) { A.storage.set('tasks', tasks); A.emit('demo:tasks-changed'); },
    log(action, entity) {
      const logs = this.logs();
      logs.unshift({ id: Date.now(), time: new Date().toISOString(), user: A.storage.get('profile', { name: 'Alex Morgan' }).name, action, entity, ip: 'Local demo' });
      A.storage.set('logs', logs.slice(0, 100)); A.emit('demo:logs-changed');
    },
    reset() {
      ['users', 'tasks', 'logs', 'profile', 'general', 'notifications', 'permissions', 'notifications-read'].forEach(key => A.storage.remove(key));
      A.emit('demo:users-changed'); A.emit('demo:tasks-changed'); A.emit('demo:logs-changed');
    }
  };
})(window.Admin);
